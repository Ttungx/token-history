# 管线与调度：多机采集、幂等写入、git 持久化、README 图表

> 状态：调研完成。日期 2026-08-05。
> 前置：`data-sources.md`（采集口径与保留期）。

## 1. 数据文件布局

**推荐：`data/{host}/{YYYY-MM-DD}.json`**

| 方案 | 跨机冲突 | 幂等难度 | 查询 |
|---|---|---|---|
| **1. `data/{host}/{date}.json`** | **结构性为零** — 两机永不写同一路径 | 简单：整文件覆盖 = 当天快照 | 需 glob 聚合 |
| 2. `data/{host}.jsonl` 追加 | 零 | 麻烦：追加不天然支持"覆盖某天" | 单机时序友好 |
| 3. `data/daily.json` 单文件 | 每次都碰同一文件，最大 | 最差：必须应用层读-合-写 | 最方便 |
| 4. `data/{date}.json` 含两机 | 每天必冲突一次 | 中：仍需应用层合并 | 方便 |

选 1 的理由：这是唯一一个把"host 是两个独立写者"从**文件路径结构上**解决掉的方案 —— 不是降低冲突概率，是让同名路径冲突**几何上不可能**。查询不便的代价后置给 Actions（见 §5）。

**`claude` vs `codex` 放内容里当 JSON key，不放路径。** 它俩是同一进程同一次运行采的，**没有冲突维度**，塞进路径只成倍增加文件数换不来安全性。放内容后"host+date 是否采集完整"用一次文件存在性检查就够，未来加第三个源只是加个 key。

---

## 2. 幂等写入规则

**统一成一条**：

```
date ∈ [today−7, today]  →  盲覆盖（overwrite）
date <  today−7          →  只允许 merge-max（每字段取 max(已存, 新读)，空补有，小不覆盖大）
```

- 近 7 天数据源本身在演变（当天持续增长、近几天可能被修正），信任新读数是完整快照
- 7 天前用 merge-max 是安全网，防止"本地 JSONL 被清理导致重算出偏小的数，反而抹掉历史上正确的大值"
- 正常情况下 per-host watermark 让脚本根本不碰 7 天前；merge-max 只兜"手动回填/重跑历史"

**当天标 `partial`、次日改 `final`** — 值得。多付出的是次日一次有意义的状态转换（不是空 commit），换来消除"这份数据是不是半成品"的永久歧义。下游画图时 partial 的当天点不该被当最终值。

---

## 3. 空 commit 与浮点

```bash
git add -A data/ && git diff --cached --quiet || git commit -m "..."
```

`git diff --cached --quiet` 隐含 `--exit-code`（`man git-diff`）：无差异退出 0（`||` 短路，不提交），有差异退出 1。

⚠️ **浮点四舍五入必须做在落盘的值本身上**，不能只在比较/hash 阶段临时 round。否则今天 round 后跳过了 commit，明天同样底层数据再算一遍又产出新尾数，规则形同虚设。（本机实测尾数噪音 ~1e-13。）

---

## 4. git 冲突处理

**`git pull --rebase` + 重试循环**是社区惯例，但没有官方规范规定重试次数。判断：5 次、退避 2/4/8/16/32s 足够。

**采用 §1 的按 host 分路径后，rebase 阶段几乎永远没有真正的文本冲突** —— 两边从不改同一行，失败只会是 non-fast-forward 的纯 ref 竞争，重试即可无脑解决，不需要写任何冲突解决逻辑。

**`.gitattributes` 的 `merge=union` 不需要用，且有坑**：
- git 官方文档自己警告："This tends to leave the added lines in the resulting file in **random order**"
- 同一 host 做 partial→final 修正时，union 会把新旧两行都留下，产生同 date 两条不同数值的记录
- ⚠️ **GitHub 网页端合并按钮不认 `.gitattributes`** —— 官方回复："GitHub doesn't consider user-defined .gitattributes files"（[community#9288](https://github.com/orgs/community/discussions/9288)）。只在真跑 `git merge`/`git rebase` CLI 时生效。

**push 失败不需要额外的暂存队列** —— git 的本地 commit 本身就是队列：

```
写文件 → git add → git commit   (不碰网络，几乎不失败)
        → pull --rebase && push  (这步才可能失败)
```

所有重试失败时本地 commit 依然完整存在，无数据丢失。下次触发照常 `pull --rebase`（把未推的 commit 一起 rebase）再重推，`git push` 默认会把所有领先 origin 的 commit 一起推上去。**唯一要加的**：连续失败超过 3 个周期时写明显警告日志。

**不建议一开始就上"各机推自己分支 + Actions 合并 main"** —— 那是把小风险（本地 push 竞争）换成大复杂度（多一层依赖 Actions 定时的管道，而 Actions 本身有 §5 的可靠性问题）。只在实测发现直接推送经常失败时才升级。

---

## 5. GitHub Actions 的定位

**只用来生成派生视图（聚合 / 图表 / README 更新），源数据完整性完全不依赖它按时跑。** Actions 迟到、丢单、连续几天不跑都不影响正确性，只影响图表新鲜度。

官方明确承认的限制：
- **会延迟**："The `schedule` event can be delayed during periods of high loads"，官方建议**别卡整点**
- **会丢单**："If the load is sufficiently high enough, some queued jobs may be dropped"
- **60 天无活动自动禁用** scheduled workflow（只有新 commit 能重置计时器，开 issue/发 release 不算）
- 只在默认分支的最新 commit 上运行

**递归防护是官方默认行为，不需要 `[skip ci]`**：
> if a workflow run pushes code using the repository's `GITHUB_TOKEN`, a new workflow will not run even when the repository contains a workflow configured to run when push events occur.

⚠️ 但**本机通过 SSH 推送用的是你自己的身份，不是 `GITHUB_TOKEN`** —— 本机 push **会**正常触发聚合 workflow。这正是想要的，别混淆。

**配额**：public repo 在标准 runner 上**免费无限**；private free 计划每月 2,000 Linux 分钟（macOS 计 10 倍）。每天 3 次 × 1 分钟 ≈ 90 分钟/月，不是瓶颈。

---

## 6. macOS 调度

### 6.1 launchd 的补跑行为

**睡眠 —— 文档明说**（`man 5 launchd.plist`，本机 macOS 15.6 核验原文）：
> Unlike cron which skips job invocations when the computer is asleep, launchd will start the job the next time the computer wakes up. **If multiple intervals transpire before the computer is woken, those events will be coalesced into one event** upon wake from sleep.

即错过 N 次，唤醒后只补 **1 次**。

**关机 —— 文档沉默**。man page 那段只讲了 sleep。社区实测一致认为关机期间错过就是跳过、不补，直接到下一个预定点。（[Apple Community 5137946](https://discussions.apple.com/thread/5137946)、[Apple Forums 815034](https://developer.apple.com/forums/thread/815034)）

⚠️ **纠正一个流传很广的错误**：网上常说「`StartCalendarInterval` 隐含 `RunAtLoad`」—— **man page 里没有这句**。真正写"隐含 RunAtLoad"的是 `KeepAlive`。两个键完全独立。

→ **靠 `RunAtLoad=true` 兜关机场景**（每次加载立即跑一次，因为幂等所以无害；副作用只是调试 bootstrap 时多跑一次）。

**补跑逻辑必须做进脚本自己，不能指望 launchd。**

### 6.2 调度频率：维持 00:30 / 12:00 / 21:00，不改每小时

不和稀泥的理由：
- 每小时能缓解的只是"某个点恰好睡眠/断网"的**瞬时**问题。三个分散的点 + 次日 00:30 + 7 天 watermark 已经能自愈，不丢数据，只丢"当天多个采样点"这种细粒度
- 每小时**完全解决不了**真正危险的场景 —— 长时间关机。出差关机两天，每小时和每天三次都是全错过，没有本质差别。对症的是 `RunAtLoad` + watermark，已覆盖
- 代价不为零：24×2 台的调度开销、日志噪音、运行重叠的边界情况
- 三个时间点大概率承载着业务含义（午间/晚间检查点），换成每小时会让这层语义消失

### 6.3 TCC / Full Disk Access：**不需要**

本机实测（当前 shell 明确**没有** FDA —— `~/Library/Safari`、`~/Library/Mail` 等 15 个路径全部 `Operation not permitted`）：

```
~/.claude      READABLE
~/.codex       READABLE
~/OpenSource   READABLE
```

**前提：repo 不能放 `~/Documents` / `~/Desktop` / `~/Downloads` / iCloud Drive / 外置卷 / 网络卷** —— 那些才是 TCC 管的。`/Users/wenkeli/OpenSource/daily_tokens` 安全。

若哪天真需要 FDA：授权对象是**解释器二进制**（`/bin/bash` 或 `node`），不是脚本文件（TCC 无法为文本文件计算 designated requirement）。且 Homebrew 的 `node` 是 **ad-hoc 签名**（CDHash 每次重编都变），`brew upgrade node` 会**静默吊销**授权（[claude-code#55661](https://github.com/anthropics/claude-code/issues/55661)）。又一个"别依赖 FDA"的理由。

`man 5 launchd.plist` CAVEATS 原文：
> Daemons and agents managed by launchd are subject to macOS user privacy protections. Specifying privacy sensitive files and folders in a launchd plist may not have the desired effect, and may prevent the job from running.

### 6.4 git 凭据：**走 SSH**

本机现状（实测）：
- `~/.gitconfig` 设了 `credential.https://github.com.helper = !/opt/homebrew/bin/gh auth git-credential`，token 在 keyring
- `~/.ssh/id_rsa` / `id_ed25519` / `id_test` **三把都无 passphrase**
- `~/.ssh/config` 有 `github.com → ssh.github.com:443`（绕 22 端口封锁）
- `ssh -T git@github.com` → `Hi keli-wen!` ✓

**当前的 HTTPS + gh 路径是最脆的**：[cli/cli#13317](https://github.com/cli/cli/issues/13317) —— keychain 读取有 ~3 秒超时，**失败时 `gh` 返回空 token 并继续以未认证身份走下去**，你看到的是莫名其妙的 403 而非凭据错误。

**SSH 不碰 keychain、不碰 ssh-agent、不碰 TCC、不怕 brew upgrade。**

```bash
git -C /Users/wenkeli/OpenSource/daily_tokens remote set-url origin git@github.com:keli-wen/daily_tokens.git
```

脚本里显式声明而非依赖继承状态：
```bash
export HOME=/Users/wenkeli
export GIT_SSH_COMMAND='/usr/bin/ssh -F /Users/wenkeli/.ssh/config -o BatchMode=yes -o IdentitiesOnly=yes -i /Users/wenkeli/.ssh/id_rsa'
export GIT_TERMINAL_PROMPT=0   # 失败快，别挂死
```

可选加固：给这个 repo 单独生成 ed25519 **deploy key**（写权限），不复用个人 `id_rsa`。

### 6.5 其他 macOS 坑

- **PATH 是 `/usr/bin:/bin:/usr/sbin:/sbin`**（实测本机运行中的 LaunchAgent）。`node`/`gh` 在 `/opt/homebrew/bin`，**必须绝对路径或在 plist 里设 `EnvironmentVariables.PATH`**
- **`/usr/bin/git` 是 Apple git**，加载 `/Applications/Xcode.app/.../git-core/gitconfig` —— 你的 `credential.helper=osxkeychain` 和 `init.defaultBranch=main` 其实来自那里，不是你的 dotfiles。Xcode 更新会变
- LaunchAgent 出现在 **系统设置 → 登录项与扩展 → "允许在后台"**，可被误关（关了不删 plist 也不跑）。任务神秘停跑先查这里
- **不要设 `SessionCreate`** —— 它把 job 扔进新的 audit session，反而脱离 Aqua 的 keychain 上下文
- LaunchAgent 默认 `Aqua` session，**GUI 登录时才加载**到 `gui/501`。本机 FileVault 开启且无自动登录，所以 job 运行时必然已有人登录过

### 6.6 plist 骨架

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.wenkeli.daily-tokens</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Users/wenkeli/OpenSource/daily_tokens/scripts/collect.sh</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/wenkeli/OpenSource/daily_tokens</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>

    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Hour</key><integer>0</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Hour</key><integer>12</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Hour</key><integer>21</integer><key>Minute</key><integer>0</integer></dict>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/Users/wenkeli/Library/Logs/daily-tokens.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/wenkeli/Library/Logs/daily-tokens.log</string>
</dict>
</plist>
```

launchd 不做 `~` 展开 —— 所有路径必须绝对。

**macOS 15+ 的正确命令**（man page 标注 `load`/`unload` 为 Legacy，Recommended alternative 是 `bootstrap | bootout | enable | disable`）：

```bash
# 安装（改了 plist 必须先 bootout 再 bootstrap，没有 reload）
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.wenkeli.daily-tokens.plist

# 若被"允许在后台"关过，需显式 enable
launchctl enable gui/$(id -u)/com.wenkeli.daily-tokens

# 立刻手动触发一次（调试）
launchctl kickstart -k gui/$(id -u)/com.wenkeli.daily-tokens

# 查状态：是否加载、下次触发、上次退出码
launchctl print gui/$(id -u)/com.wenkeli.daily-tokens

# 卸载
launchctl bootout gui/$(id -u)/com.wenkeli.daily-tokens
```

调试第一步永远是配 `StandardOutPath` + `StandardErrorPath`。TCC 拒绝表现为 **EPERM**（`Operation not permitted`），POSIX 权限问题是 EACCES，两者要分清。

---

## 7. 现有轮子

### 7.1 唯一对口的：`Baek-Seunghyun/ai-coding-usage-card`

- 24★ / 10 fork / MIT，创建 2026-07-15，最近 push 2026-07-23 —— **只有约 3 周历史，非成熟项目**
- 调 `npx -y ccusage@latest --json`（**不锁版本**）；每设备一份 `cards/devices/<device>.json`；按天取 max 高水位合并
- 明确**禁止**跨机同步日志目录，处理方式是**按设备分别记账再相加**，不做会话级去重
- 官方声明**不提供自动 recall/backfill**，但高水位合并有隐式补跑效果
- 产出 4 种贡献图风格 SVG 提交进 repo，本机 cron/launchd 跑（**不是 Action** —— 云端读不到 `~/.claude`）
- README 建议多设备错开时间（如 09:37/09:42/09:47）避免 git 冲突

对照本项目需求：跨机合并 ⚠️（是分别记账不是去重）、recall window ⚠️（隐式）、weekly chart ⚠️（是 heatmap 不是周图）、day-to-day 明细 ⚠️（在 snapshot JSON 里，非逐日可读）。

**可直接借用**：按天取 max 的高水位合并算法（代码量很小）。

### 7.2 其余方向均未找到

`claude code usage badge` / `claude token usage action` / `codex usage readme` / `claude code usage readme` —— gh search **全部返回空**。

`claude-code-stats` 系（AeternaLabsHQ 29★、dmelo 19★、nermalcat69 5★）、`llm-usage-tracker` 系、以及热门的 `Maciek-roboblog/Claude-Code-Usage-Monitor`（8,590★）、`Iamshankhadeep/ccseva`（800★）—— **全是本机 dashboard/menubar，不写回 git/README**，是另一条产品线。

**结论：「本机采集 → git 持久化 → README 图表」这个细分只有一家在做，且很不成熟。自建是合理选择。**

### 7.3 waka-readme 家族的可借鉴手法

`athul/waka-readme` 1,830★（2026-08-01 更新）、`anmol098/waka-readme-stats` 3,976★（2026-08-04 更新）。

- **README 自动更新**：`<!--START_SECTION:waka-->` … `<!--END_SECTION:waka-->` 标记区间正则整段替换。**这套手法验证了多年、生态成熟，可直接照搬。**
- **图表形式：ASCII bar chart**，用 `BLOCKS` 环境变量自定义字符（`░▒▓█` / `⣀⣄⣤⣦⣶⣷⣿`）。零依赖、零图床、纯 Markdown 渲染
- ⚠️ 它们的调度是纯 GitHub Actions（因为读的是 WakaTime **云端 API**），**本项目不能照搬这一点** —— 数据源在本机

---

## 8. README 图表渲染的约束

| 方案 | 结论 |
|---|---|
| **ASCII / emoji bar chart 直写 markdown** | 最稳。零依赖、无缓存问题、无隐私风险。waka-readme 生产验证多年 |
| **SVG 提交进 repo + `<img>` 引用** | 可行且可控。⚠️ 见下面的缓存坑 |
| **mermaid `xychart-beta`** | GitHub 原生渲染 mermaid，但内置版本滞后于上游（上游 2026-03 还在修 xychart 标签遮挡）。够用但可控性差 |
| **quickchart.io 等第三方图床** | 不建议。120 req/min/IP 限流、免费额度 1000 charts/月；且图表配置（含你的用量/花费数据）编码在 URL 里发给对方服务器 |

### 8.1 缓存坑（务必绕）

- **camo（`camo.githubusercontent.com`）只代理 GitHub 域外的图片**（shields.io 等）
- **`raw.githubusercontent.com` 不走 camo，但有自己独立的 CDN 缓存**（社区观察默认 ~5 分钟，个别情况 `Cache-Control: max-age=86400` 即 24 小时）—— 这才是"commit 了新图但页面还是旧的"的真实原因（[community#46773](https://github.com/orgs/community/discussions/46773)、[#46758](https://github.com/orgs/community/discussions/46758)）
- **唯一可靠绕法**：URL 后拼时间戳或 commit-sha 作 query string（`?v=<sha>`），改变 URL 即改变缓存 key。**不能依赖"等缓存过期"**

### 8.2 SVG sanitize 边界

- 原始 `<svg>` 标签直接粘进 Markdown 会被 sanitizer 剥 `<script>` 等
- 但**通过 `<img src="x.svg">` 引用时，SVG 内部的 `<style>`（含 `@keyframes` 动画）会被保留并正常渲染**
- ⚠️ SVG 内的 `prefers-color-scheme` 跟随**浏览器/系统**颜色偏好，**不跟随 GitHub 站内的明暗主题开关** —— 两者可能不一致
- GitHub 官方推荐的暗色方案是 `<picture>` + `<source media="(prefers-color-scheme: dark)">` + fallback `<img>`，取代旧的 `#gh-dark-mode-only` fragment 技巧

---

## 9. 数据形态的一个现实问题

本机实测（Claude 侧，Asia/Shanghai）：

```
2026-08-04   input 22,160   output 776,447   cache_creation 2,829,605   cache_read 76,486,943
```

**`cache_read` 比 `output` 大 100 倍。** 如果 weekly chart 画"total tokens"堆叠柱，**99% 的面积会是 cache_read**，output 那条线根本看不见。

主指标选什么（total / output / 分开双尺度）是个必须先定的设计决策，不是实现细节。
