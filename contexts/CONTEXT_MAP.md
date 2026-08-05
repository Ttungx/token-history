# CONTEXT_MAP

`daily_tokens` 的 durable context 索引。新增 context 时在此登记。

## 约定

- 一个文件一个主题，文件名用 kebab-case
- 每份 context 开头标注**状态**和**日期**
- 严格区分「实测证明」与「推断」；未解决的事项单列一节，**不要圆过去**
- 数字必须可复现 —— 给命令或文件路径，不给"大约"

## 索引

| 文件 | 主题 | 状态 |
|---|---|---|
| [`decisions.md`](./decisions.md) | **用户拍板的方向性决策** —— 产品定位、repo 可见性与脱敏、图表投递、指标、Codex 范围、明细粒度 | 完成 |
| [`data-sources.md`](./data-sources.md) | Claude Code / Codex CLI 本地数据的位置、schema、去重口径、保留期与 recall window、ccusage 各版本状态 | 完成，含 1 项未解决 |
| [`pipeline-and-scheduling.md`](./pipeline-and-scheduling.md) | 文件布局、幂等规则、git 冲突处理、GitHub Actions 定位、macOS launchd 调度、README 图表渲染约束、现有轮子调研 | 完成 |

## 项目目标（一句话）

两台 macOS 每天 00:30 / 12:00 / 21:00 采集本机 Claude Code + Codex 的 token 用量，幂等地持久化进
`github.com/keli-wen/daily_tokens`（对抗本地 30 天清理），并在 README 展示 weekly chart。

## 当前未解决

0. **repo 只留了 30 天，但"两来源齐全"的完整区间是 52 天** — 见 `decisions.md` D9。
   多出的 21 天 Claude 数据在清理倒计时上，要补趁早。
1. **Codex 侧口径分歧 31%** — ccusage v20 报 36,945,083，自研解析器报 53,206,631。谁对未知。
   见 `data-sources.md` §4.6。已按 `decisions.md` D1a **双记兜住，不阻塞上线**。
2. **第二台机器的环境未勘察** — ccusage 版本、Codex 是否装、路径是否一致均未知。部署时的实地问题。

（原「主指标未定」「synthetic」「订阅还是 API 计费」三项已在 grill 中解决，见 `decisions.md` D4 与「未问/已延后」。）

## 已定的地基（不再讨论）

- Claude 侧：升级 ccusage 到 v20 即可，逐字段对账通过；旧版 v15.7.1 少报 38.93%
- Codex 侧：累加 `last_token_usage`（非 `total`），按事件 timestamp 分桶，`(ts,in,out)` 文件内去重
- 两侧字段语义不同：Codex 的 `input_tokens` **包含** cached，Claude 的是分开的
- 时区固定 **Asia/Shanghai**，写进记录
- 布局 `data/{host}/{YYYY-MM-DD}.json`，`claude`/`codex` 作 JSON key
- 幂等：近 7 天盲覆盖，7 天前只 merge-max
- watermark **per-host**
- git 走 **SSH**，脚本内所有可执行文件绝对路径
- 调度维持 00:30/12:00/21:00 + `RunAtLoad=true`，补跑逻辑做进脚本
- Actions 只生成派生视图，源数据完整性不依赖它
