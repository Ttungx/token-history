# 数据源：Claude Code 与 Codex CLI 的本地 token 用量

> 状态：调研完成，含 1 项未解决。日期 2026-08-05。
> 所有数字为 keli-wen 本机（macOS 15.6，Darwin 24.6.0）实测。

## 1. Claude Code

### 1.1 文件位置与发现

```
~/.claude/projects/**/*.jsonl        # 递归，含 subagents/
```

- `subagents/` 占 **54% 的 assistant 行**（22,644 / 42,104），且与主会话**零重复**
  （`isSidechain=true` 的行数恰好等于 subagent 行数，跨"主文件↔subagent 文件"的重复组为 0）
- 嵌套可达深度 6：`projects/<proj>/<uuid>/subagents/workflows/wf_*/agent-*.jsonl`
- 环境变量 `CLAUDE_CONFIG_DIR` 支持逗号分隔多路径；设置后**完全替换**默认路径
  （默认路径为 `${XDG_CONFIG_HOME:-~/.config}/claude` 和 `~/.claude`，两个都存在则都扫）

### 1.2 行 schema

只有 `type == "assistant"` 的行带 usage。相关字段：

| 路径 | 说明 |
|---|---|
| `timestamp` | ISO8601，UTC |
| `message.id` + `requestId` | 去重键的两半 |
| `message.model` | 如 `claude-opus-5`、`<synthetic>` |
| `message.usage.input_tokens` | 与 cache_read **分开计** |
| `message.usage.output_tokens` | ⚠️ 见 1.3 |
| `message.usage.cache_creation_input_tokens` | = 下面两项之和 |
| `message.usage.cache_creation.ephemeral_5m_input_tokens` | |
| `message.usage.cache_creation.ephemeral_1h_input_tokens` | 本机占 cache creation 的 55.6%，**计价更贵** |
| `message.usage.cache_read_input_tokens` | |
| `message.stop_reason` | 真值行非空，占位行为 `None` |

本机数据中**不存在 `costUSD` 字段**。

### 1.3 关键陷阱：同一次 API 调用被写成多行

Claude Code 把一次 API response 的每个 content block 写成一行，共享同一 `message.id` + `requestId`。存在**两种形态**（全库普查，16,144 个唯一组）：

| 形态 | 组数 | 说明 |
|---|---|---|
| 单行 | 2,723 | 无歧义 |
| 多行且 `output_tokens` 恒定 | 7,207 | 最终 usage 重复写在每行上，取任意一行都对 |
| 多行且 `output_tokens` 递增 | **6,198** | 前几行是占位小值，最后一行才是真值 |

递增形态的实例（`msg_01BskaBd9EoS9tgW`）：

```
out=3      blocks=['thinking']  content_chars=203,333 (~50,833 tok)  stop=None
out=3      blocks=['text']      content_chars=117                    stop=None
out=54,509 blocks=['tool_use']  content_chars=304                    stop=tool_use
```

**正确算子：按 `(message.id, requestId)` 分组取 `max(output_tokens)`。**
`max` 对两种形态都正确；`sum` 会把恒定形态炸成 N 倍（曾见 48 行同值）。

首行 vs max 的全库差距：13,625,367 vs 22,312,654 = **少报 38.93%**。

### 1.4 日期归属

按 `timestamp` 分桶，**必须固定时区并写进记录**。实测同一天在 `Asia/Shanghai` 与 `UTC` 下成本差 13%。本项目固定 **Asia/Shanghai**。

### 1.5 本机现状

16,144 个唯一组，覆盖 **42 天**，跨度 `2026-06-15 .. 2026-08-05`。

---

## 2. Codex CLI

### 2.1 文件位置

```
~/.codex/sessions/{YYYY}/{MM}/{DD}/rollout-*.jsonl
~/.codex/archived_sessions/rollout-*.jsonl        # 平铺，必须一起扫
```

- `archived_sessions` 是**手动归档、move 语义**，与 `sessions/` **零 id 重叠**（179 vs 1049）
- 归档文件内容完整，`token_count` 事件齐全 — **漏扫会少数据**
- ⚠️ 二进制含 `local_thread_store_compression` 特性开关，产物 `.jsonl.zst`，outcome 含 `removed`。
  当前未启用（`.zst` 文件数为 0），但 **glob 应从第一天起同时匹配 `*.jsonl` 和 `*.jsonl.zst`**，
  否则一旦上游开启会静默漏数据。

### 2.2 事件 schema

取 `payload.type == "token_count"`：

```json
{"timestamp":"...","type":"event_msg","payload":{"type":"token_count","info":{
  "total_token_usage":{...}, "last_token_usage":{...}, "model_context_window":258400},
  "rate_limits":{...}}}
```

**`last_token_usage` 是本轮增量，`total_token_usage` 是会话累计。** 实测精确验证：

```
sum(last.output) = 8,537       final total.output = 8,537      ✓
sum(last.input)  = 2,189,545   final total.input  = 2,189,545  ✓
total_tokens 单调非递减 ✓        每个事件都带 timestamp ✓
```

**正确口径：累加 `last_token_usage`，按每个事件自己的 timestamp 分桶。**
取会话末尾的 `total` 会把跨天会话整个算到最后一天。

### 2.3 与 Claude 的字段语义差异（合并时的陷阱）

**Codex 的 `input_tokens` 包含 `cached_input_tokens`；Claude 的 `input_tokens` 与 `cache_read_input_tokens` 是分开的。**

实测印证（2026-08-01）：我的 `input − cached` = 1,885,144 − 1,722,624 = 162,520，与 ccusage 的 `inputTokens` 完全相等。

→ 归一化时 Codex 的"非缓存输入" = `input_tokens − cached_input_tokens`。

### 2.4 去重

- **跨文件重复：0**（1233 文件、92,599 事件，按 `(ts, in, out)` 检查）
- **无 fork replay 问题** — `session_meta` 里根本没有 fork/parent 指针
- **文件内重复 741 对，全部相邻**（连续两行完全相同）；另 6 对非相邻但值为 `(0,0)`
- 不去重的膨胀：**0.951%**（53,668,256 vs 53,162,626）

→ 按 `(timestamp, input_tokens, output_tokens)` 文件内去重即可。

### 2.5 originator 分布（全期 output）

| originator | files | out_tokens | share |
|---|---|---|---|
| Codex Desktop | 1075 | 46,777,480 | 87.9% |
| codex_vscode | 47 | 2,845,957 | 5.3% |
| codex_cli_rs | 43 | 2,443,101 | 4.6% |
| CodexMobile | 18 | 710,754 | 1.3% |
| codex-tui | 10 | 347,897 | 0.7% |
| codex_exec | 24 | 64,991 | 0.1% |
| Claude Code | 5 | 19,114 | 0.0% |

**绝大部分用量来自 ChatGPT.app 的 Codex Desktop，不是 CLI。** 这影响"要统计什么"的定义。

### 2.6 无清理机制

`config.toml` 全文无任何 retention/cleanup 键。`sessions/2025-09-04` 的文件（11 个月前）仍完整可读。`session_index.jsonl` 里 666 个 id 在磁盘上**零丢失**。

（`max_rollout_age_days` 存在但属于 `[memories]` 段，是记忆固化时的**读取作用域**，不是删除策略。）

---

## 3. 保留期与 recall window

### 3.1 Claude Code 的清理机制

- `cleanupPeriodDays` **默认 30 天**，`0` = 禁用
- 判定依据是**文件 mtime**，从不读文件内容
- 清理粒度：父 `<uuid>.jsonl` 过期被删时，`rm -rf <uuid>/` 整个目录连根拔起
- **父存活豁免**：父 transcript 存在且未过期时，其 `subagents/` 树被**完全跳过**，内部文件多老都不删

### 3.2 与本机观测的对账

表面矛盾：`2026-08-04 − 30d = 2026-07-05`，但机器上有 `2026-06-15` 的文件。

已消解：那 166 个老文件**全部在 `subagents/` 里**，父 transcript mtime 是 7/10~7/11（存活）。真正被扫描的顶层 transcript，最老一个是 `2026-07-04T08:05:18Z`；`.last-cleanup`（`2026-08-03T05:55:05Z`）减 30 天 = `2026-07-04T05:55:05Z`，**差 2 小时 10 分，前面一个文件都没有**。30 天边界精确吻合。

### 3.3 `.last-cleanup` 不是每日限流

marker 的 24h 新鲜期只能把清理**推迟 10 分钟**（状态机第二次 tick 不复查哨兵）。本机 8/3 当天实测跑了 **3 次**清理。**没有宽限期可吃。**

（文档说 "deletes at startup"，实际是启动后 5 秒的后台延迟任务 + 用户空闲 60s 门控。文档与代码不一致。）

### 3.4 硬保证与窗口建议

**推导**：删除谓词是 `mtime < now − 30d`，而文件 mtime ≥ 文件内任何一条消息的时间戳
⇒ 日历日 D 的记录只存在于 mtime ≥ D 的文件中
⇒ **任意一天 D 的 Claude 数据，保证在 D 起 30 天内可读。**

| 阶段 | 窗口 | 说明 |
|---|---|---|
| 防清理（repo 尚未持久化） | **21 天** | 从 30 扣：截止线非午夜 −1、UTC/CST 时区 −1、另一台机器 `cleanupPeriodDays` 未知 −4、清理随时触发无宽限 −3 |
| 防漏跑（repo 已持久化） | `clamp(距上次成功运行 + 2, 3, 21)` | **watermark 必须 per-host** — 否则 A 机每天跑会把 B 机的 watermark 推平 |

Codex 侧无清理约束，窗口只受"防漏跑"驱动。

### 3.5 比窗口大小更重要的三条

1. **写入非破坏化**：`date < today−7` 的日子只允许**补空和向上修正（merge-max）**，禁止向下覆盖。
   窗口边缘那天可能"部分文件已过期"，覆盖式写入会把原本正确的数字**改小** —— 漏采看得出来，改小看不出来。
2. **运行时读实际配置**：`W = min(W, (settings.cleanupPeriodDays ?? 30) − 7)`。
   合并顺序 managed policy > user settings > 默认 30。另一台机器可能设了更小值，managed settings 还不可见。
3. **扫描路径要全**（见 1.1 / 2.1）。

### 3.6 失效场景

| 场景 | 是否被 21 天覆盖 |
|---|---|
| 连续关机 ≤ 21 天 | ✅ |
| 连续关机 22–30 天 | ⚠️ 靠非破坏化写入兜底 |
| 连续关机 > 30 天 | ❌ Claude 侧确定性丢失，任何窗口都救不了 |
| 某机器设了 `cleanupPeriodDays: 14` | ❌ 必须靠 runtime clamp |
| 用户在 Codex UI 手动 delete 线程 | ❌ 无法防御 |
| Codex 启用 zstd 压缩 | ❌ 必须靠 glob 兼容 `.zst` |

---

## 4. ccusage 的状态（重要修正）

### 4.1 本机装的是过期版本

- 本机：`/opt/homebrew/bin/ccusage` **v15.7.1**（包 mtime 2025-08-06）
- npm latest：**v20.0.19**（2026-07-27）
- 仓库已从 `ryoppippi/ccusage` 迁到 **`ccusage/ccusage`**（17,727★，仍在日更）

### 4.2 v15.7.1 确实有 1.3 描述的 bug

受控实验（`CLAUDE_CONFIG_DIR` 指向只含 3 行 `2/2/999` 的夹具）：

```
v15.7.1 → outputTokens = 2        # 取先遇到的
逆序 999/2/2 → outputTokens = 999 # 确认是"取第一条"不是"取最小"
```

去重函数 `createUniqueHash = ${message.id}:${requestId}`，全局 `Set`，先查后加。

### 4.3 上游已修复，且修法与本文 1.3 推导一致

相关 issue 全部已关闭：
[#705](https://github.com/ccusage/ccusage/issues/705)、[#797](https://github.com/ccusage/ccusage/issues/797)、
[#866](https://github.com/ccusage/ccusage/issues/866)、[#888](https://github.com/ccusage/ccusage/issues/888)、
[#901](https://github.com/ccusage/ccusage/issues/901)、[#938](https://github.com/ccusage/ccusage/issues/938)
（"First-wins dedup keeps partial streaming output_tokens"）。2026-05-17 集中修复。

当前 `main` 的 `rust/adapters/claude/src/daily.rs`：

```rust
if candidate_total != existing_total {
    return candidate_total > existing_total;   // 取 total token 更大的那条
}
```

### 4.4 v20 与本文算法逐字段对账成功（Claude 侧）

| date | v20 out | 本文算法 | v20 in | 本文 | v20 cc | 本文 cc_5m+cc_1h |
|---|---|---|---|---|---|---|
| 08-02 | 220,300 | **220,300** ✓ | 370 | **370** ✓ | 1,454,521 | 348,206+1,106,315 = **1,454,521** ✓ |
| 08-03 | 237,117 | **237,117** ✓ | 375 | **375** ✓ | 1,586,700 | 169,846+1,416,854 = **1,586,700** ✓ |
| 08-04 | 776,447 | **776,447** ✓ | 22,160 | **22,160** ✓ | 2,829,605 | 1,864,996+964,609 = **2,829,605** ✓ |

**Claude 侧：升级到 v20 即可，无需自写解析器。**

### 4.5 v20 是个不同的产品

`daily` 现在聚合**所有检测到的 coding CLI**，并有独立子命令：
`claude` / `codex` / `opencode` / `amp` / `droid` / `codebuff` / `hermes` / `pi` / `goose` / `kilo` / `copilot` / `gemini` / `kimi` / `qwen` / `openclaw`

即**原生同时支持 Claude + Codex**，正是本项目所需。

### 4.6 ⚠️ 未解决：Codex 侧 v20 与本文算法差 31%

```
ccusage v20:      201 days   out = 36,945,083
本文算法 live only:     196 days   out = 44,998,756
本文算法 live+archived: 201 days   out = 53,206,631
```

ccusage 天数与 live+archived 相同（说明它读了归档），但 output 比本文算法**低 31%**，甚至低于只扫 live 的数字。

**已排除的解释**：
- 归档目录 —— 天数吻合，说明它读了
- originator 过滤 —— 排除所有 `*vscode*` 后仍有 50.4M，离 36.9M 很远
- 日内漂移 —— 08-04 是已结束的日子，仍差 52,645

**本文算法的自洽证据**：单文件内 `sum(last.output)` 精确等于 `final total.output`。

**谁对未知。** 解决需要读 ccusage v20 的 Rust Codex adapter 源码。在此之前，Codex 侧的数字**不要当作已确定**。

### 4.7 v15.7.1 的其他缺陷（若坚持用旧版才相关）

- `--offline` 内置价格表最新只到 `claude-4-opus-20250514`，不含 opus-5 → `totalCost: 0`
- 默认每次运行都联网下载 LiteLLM 价格表 1.67MB，**无磁盘缓存**
- **网络失败静默降级**：JSON 模式下 `logger.level=0` 吞掉警告 → stdout 合法 JSON、cost=0、exit 0、stderr 空
- `--since/--until` 在聚合**之后**才过滤 —— 不省任何 I/O（全量 5.10s vs 单日 5.01s）
- `ccusage session` 在当前目录布局下已损坏（把 `sessionId` 解析成 `"subagents"` 和项目名）
- 忽略 `cache_creation.ephemeral_1h_input_tokens` 的溢价（LiteLLM 有 `cache_creation_input_token_cost_above_1hr`）

### 4.8 稳定性（v15.7.1 实测，v20 未复测）

- **已结束的日子：byte-identical**，与 `--since` 窗口无关
- **当天在增长**：几分钟内 `out` 从 268,505 → 268,542
  → **幂等只能 overwrite by date，不能 append**
- 浮点求和顺序不稳定：`61.86139775000001` vs `61.861397750000066`（差 ~1e-13）
  → **四舍五入必须做在落盘的值本身上**，不能只在比较/hash 时临时 round

---

## 5. 尚未回答

1. **Codex 侧 31% 分歧**（4.6）—— 需读 ccusage v20 Rust Codex adapter 源码
2. v20 是否仍有 4.7 的网络失败静默 cost=0 问题
3. v20 的 `--since` 是否仍不省 I/O
4. `<synthetic>` 模型怎么处理（v15 把它排除出 breakdown 但仍计入 totals，导致两者对不上）
5. Codex 走 ChatGPT 订阅还是 API 计费 —— "成本"维度是否有意义
