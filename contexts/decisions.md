# 已决策

> 状态：grill 完成。日期 2026-08-05。
> 前置：`data-sources.md`（采集口径）、`pipeline-and-scheduling.md`（管线与调度）。
> 这里只记**用户拍板的方向性决策**。有实测支撑的技术事实在前两份里。

## D1. 产品定位：ccusage 之上的增量层

**依赖 ccusage 作为唯一采集层**（用 `@latest`，见下方修订）。本项目的价值 = ccusage **明确不做**的四件事：

1. 持久化（对抗本地 30 天清理）
2. 多机合并
3. 图表自动生成
4. 稳定 URL

不重复造解析器。理由：ccusage 17.7k★ 日更，已是「解析本地 coding CLI 日志」的事实标准，原生支持 15 种 CLI；fork 本项目的人若用 Gemini/Copilot/OpenCode 等能白拿支持。

**Claude 侧 v20 已逐字段对账通过**（见 `data-sources.md` §4.4），包括 cost —— v20 报 08-03 为 `$70.7048`，与独立计算的「取 max output + 1h 缓存溢价」修正值完全吻合（v15 报 `$61.86`）。**v20 把 output 少报和 1h 缓存溢价两个问题都修了。**

~~⚠️ pin 版本而非 `@latest`~~ **已修订**：用户选 `@latest`，且这个直觉更对 —— v15 那个坑恰恰是因为本机装了一年前的版本再没升过，`@latest` 反而永远拿到上游修复。
补偿措施：**每个数据文件写入 ccusage 版本号**（`ccusageVersion` 字段）。将来上游行为再变（像 v15→v20 跳 38%），时间序列上的台阶能立刻查出是哪天换的版本。

### D1a. Codex 侧双记 —— ~~已砍~~

曾提议把自研解析器的 Codex 数字作为第二字段并记以兜住 31% 分歧。**用户明确否决**：「只依赖 ccusage，不用自研」。

结果：Codex 数字**默认采信 ccusage**，31% 分歧仍未解且无本地对照物。若将来要查，`data-sources.md` §4.6 里有完整的复现方法和已排除的假设。

## D2. repo 公开 + 脱敏 + 可 fork

**公开** `github.com/keli-wen/daily_tokens`。

**脱敏红线**（公开 repo 里绝不能出现）：
- 项目名 / `cwd` / 文件路径 / git 分支
- 真实机器名 —— host 用中性别名（`mac-a` / `mac-b`），映射关系不进 repo

**可 fork 复用**是显式设计目标，不是附赠。意味着：
- 无硬编码路径，所有环境相关项进配置文件
- 通用安装脚本 + 清楚的 setup 文档
- 别人 fork → 改配置 → 能跑

## D3. 图表投递：固定 URL，容忍缓存延迟

`daily_tokens` 里生成固定路径的图，用户在 profile README 引用一次即可，**不需要任何 profile repo 的写权限**。

接受 `raw.githubusercontent.com` CDN 缓存导致的数小时滞后。理由：数据是日粒度、每天只采 3 次，滞后几小时看不出来；换来的是 fork 者 setup 最简单（零跨 repo 权限）。

放弃的方案：Actions 回写 profile README 换 `?v=<sha>`（需要 PAT，fork 者也得各配一个）。

## D4. 两张图：tokens + cost USD

用户明确要两张。且用户认为「**图好不好看是这类项目热不热门的核心**」—— 视觉质量是一等公民，建的时候按 dataviz 规范认真做。

- **堆叠维度按来源（claude / codex），不按 token 类型。** 按类型堆叠会被 `cache_read` 占满 99% 变成纯色柱；按来源堆叠两边量级可比（08-04：Claude ≈ 80.1M，Codex ≈ 113.1M）
- **cost 必须标注为「API 等价价值」而非实际支出。** 用户是订阅制（本会话撞到过 `session limit · resets 5:20pm`），ccusage 的 `totalCost` 算的是「按 API 价格值多少钱」。这是个更好的 flex（"$200/月订阅榨出 $X 等价用量"），但标签写错就是误导

## D5. Codex 范围：全算

Desktop + VSCode + CLI + Mobile 全部计入。理由：共用同一份 ChatGPT 订阅额度，从「我每天用了多少 AI」的角度本就该合并；且 ccusage v20 默认就这么算，无需过滤逻辑，fork 者行为一致。

（分布参考：Codex Desktop 87.9%、codex_vscode 5.3%、codex_cli_rs 4.6%、CodexMobile 1.3%、其他 0.8%。若当初只算命令行，数字会缩水 ~90%。）

## D6. 明细粒度：天 × host × 来源 × model

**不可逆决策** —— 超过 30 天窗口的历史无法重建，粒度必须一次定对。

`modelBreakdowns` 是 ccusage 白送的，存下来零成本。将来想画「模型占比变化」「opus 占比趋势」无需重新采集（也采不到了）。体积量级：每天每机几 KB，一年几 MB。

不做 per-project（即使哈希化）—— 公开 repo 里「项目数量和切换频率」本身也是信息泄露。

---

## 未问 / 已延后

| 项 | 为什么可以先放着 |
|---|---|
| `<synthetic>` 模型的处理 | 默认**单列一行、不混入真实模型明细、不计入 cost**。可逆，跑起来看到真实占比再调 |
| 第二台机器的实际环境 | 只勘察了当前这台。另一台的 ccusage 版本、Codex 是否装、路径是否一致都未知 —— 属于部署时的实地问题，不影响设计 |
| Codex 31% 分歧的根因 | 已按 D1a 双记兜住。查清需读 ccusage v20 的 Rust Codex adapter 源码，是开放式任务，不阻塞上线 |
| 图表的具体视觉设计 | 实现阶段的事，不是方向性决策 |
| 首日是否回填 42 天历史 | 显然要 —— 且**越早越好**，06-15~07-04 那批靠父存活豁免苟着，父文件一过期整棵消失 |

---

## 实现阶段追加的决策（2026-08-05）

### D7. 运行入口：`uv run` 锁解释器，非 venv

零依赖项目不需要 venv —— 没有包可隔离，只会给 fork 的人多一个会失败的步骤。真问题是**解释器漂移**：本机交互式 shell 是 anaconda 3.11.5，launchd 下是 `/usr/bin/python3` 3.9.6。同一脚本手动测和凌晨自动跑用的不是同一个解释器。

方案：**PEP 723 内联元数据 + `scripts/run.sh`**，uv 在场时按 `.python-version` 锁定，缺席时退化到 `python3`。两条路产出的 SVG 已验证**字节完全一致**。

⚠️ 实测坑（uv 0.6.5）：**`uv run` 不会自动读 `.python-version`** —— `--project .` 和在 repo 根目录裸跑都静默继承环境里的 python。必须显式传 `--python`，否则整个 wrapper 的目的落空。

**已修订（2026-08-05 晚）：改为 repo 级 uv 项目。** 用户要求 `pyproject.toml + uv sync / uv run` 的标准 uv 工作流：

- 新增 `pyproject.toml`（`requires-python >=3.9`、零依赖、`[tool.uv] package = false` —— 脚本仓不是可安装包）+ 提交 `uv.lock`
- **PEP 723 头从两个脚本里移除** —— 带着它 `uv run` 会切到 script 模式，而 script 模式不读 `.python-version`；**项目模式原生尊重 `.python-version`**（实测 uv 0.6.5 自动取到 3.12），上面的 `--python` 坑不再适用
- `run.sh` 改为 `uv run --project "$REPO"`；python3 兜底保留（脚本仍 stdlib-only、3.9 兼容，D2 可 fork 性不变）
- CI 从 setup-python 换成 `astral-sh/setup-uv` + `uv run scripts/render.py`

### D8. 图表：默认 30 根日柱，不是周柱

原计划 16 周周柱。实际渲染后用户判断「16 周的 bar plot 不那么直观」。30 天窗口下周聚合只剩 4~5 根粗柱，比 30 根细柱更难读，也丢掉了日节奏。

`--weeks N` 仍可切回周粒度。输出文件名去掉粒度前缀（`charts/tokens.svg` / `charts/cost.svg`），保证 URL 稳定。

### D9. repo 里只保留最近 30 天

用户：「不完整的数据我不喜欢」。

⚠️ **需要复核的取舍**：按「两个来源都有数据」这个标准，完整区间其实是 **2026-06-15 起共 52 天**（Claude 起点），不是 30 天。裁到 30 天丢掉了 07-06 之前 21 天的 Claude 数据，而那部分正在 30 天清理倒计时上，**过期后不可恢复**（Codex 那半边随时可补，它无清理机制）。

完整 201 天已备份在 session scratchpad 的 `data-backup/`。改回 52 天是一条命令的事，但**要趁 Claude transcript 还没过期**。

### D10. 配色与字体:Anthropic 品牌,同色相微调至过校验

用户拍板(2026-08-05 grill):

- **Claude=橙、Codex=蓝**(与最初实现对调)。理由:Claude 是 Anthropic 产品,穿品牌主 accent 橙 #d97757 系;蓝 #6a9bcc 系作 secondary 给 Codex。当时 repo 未推广,切换代价接近零
- **官方 hex 不逐字节照搬,保色相微调至 dataviz 校验全过**。官方原值的实测失败项:亮色下蓝 #6a9bcc 饱和度低于 chroma floor(发灰)且对表面对比仅 2.85:1;暗色下两色明度都出 [0.48, 0.67] 带
- 最终值(`validate_palette.js` 全过,改动后必须复验):亮 `#d06a41 / #4382c9`(surface `#faf9f5`,worst CVD ΔE 20.0);暗 `#db7448 / #5b95d6`(surface `#141413`,worst CVD ΔE 18.5)
- 中性色与表面直接用品牌值:`#141413` / `#faf9f5` / `#b0aea5` / `#e8e6dc`;日历类 ramp 用品牌橙单色阶(明度单调,亮暗各自独立取档)
- 字体按品牌:标题 Poppins(Arial 兜底)、正文 Lora(Georgia 兜底)。`<img>` 内嵌 SVG 加载不了 webfont,兜底栈就是品牌指定的兜底

### D11. README = 全展开的图表 catalog + uv-first 英文教程

- **图库全部展开、不折叠**。README 同时是「别人来挑图的 catalog」和「SVG 在 GitHub README 里实际渲染效果的实验场」。用户自己的用法:profile README 只挑一两张引用
- 图表按粒度进 `charts/{day,week,month}/`,每粒度多风格(bar / calendar / area / card / ledger),全部每次 render 都重新生成;`charts/tokens.svg` / `cost.svg` 保留为日粒度 bar 的稳定别名(D3/D8 的 URL 承诺不破)
- Quick start 改 **uv-first**(英文),含 uv 安装与 `uv run --python` 用法;python3 兜底保留(D7 不变)
- 改完即 commit + push 线上验收(用户确认)
