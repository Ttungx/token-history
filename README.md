# daily_tokens

A durable, self-updating record of how much AI coding I actually use — and a pair of charts you can drop into a GitHub profile README.

The repo keeps a day-by-day history; the charts show the last 30 days.

<img src="./charts/tokens.svg" width="880" alt="Daily token usage, stacked by source">

<img src="./charts/cost.svg" width="880" alt="Daily API-equivalent value, stacked by source">

📊 **[Full numbers → SUMMARY.md](./SUMMARY.md)** · day-by-day history in [`data/`](./data)

---

## Why this exists

Claude Code deletes session transcripts older than `cleanupPeriodDays` — **30 days by default**. Every tool that reports your usage, [`ccusage`](https://github.com/ccusage/ccusage) included, reads those transcripts. So your history isn't archived anywhere; it's on a rolling 30-day delete, and once a day falls off the edge no tool can recover it.

This repo snapshots the numbers into git before that happens. Three times a day, on each machine, idempotently.

It is **not** another usage parser. ccusage already does that job well and supports ~15 different coding CLIs. This adds the four things ccusage deliberately doesn't do:

| | |
|---|---|
| **Persist** | daily JSON in git, immune to local cleanup |
| **Merge** | several machines into one timeline |
| **Render** | two charts, regenerated automatically |
| **Serve** | a stable URL you reference once and never touch again |

## Quick start

**Prerequisites:** Node (for `npx ccusage`) and either [uv](https://docs.astral.sh/uv/) or any Python ≥ 3.9.

```bash
git clone https://github.com/<you>/daily_tokens && cd daily_tokens
cp config.example.json config.json     # set "host" to an alias like mac-a
./scripts/run.sh collect --all         # backfill everything ccusage still has
./scripts/run.sh render                # build the charts locally
```

Then schedule it (macOS):

```bash
./scripts/install-launchd.sh           # 00:30 / 12:00 / 21:00 + every login
```

Not on macOS, or prefer a different trigger? The collector is fully self-contained, idempotent, and backfills its own gaps — so **anything** that calls it periodically works: cron, a systemd timer, a line in your shell profile, or running it by hand. The scheduler is not load-bearing.

To show the charts elsewhere, reference the raw URLs:

```markdown
![tokens](https://raw.githubusercontent.com/<you>/daily_tokens/main/charts/tokens.svg)
![cost](https://raw.githubusercontent.com/<you>/daily_tokens/main/charts/cost.svg)
```

The URL is stable — no cache-busting query, no write access to your profile repo, nothing to maintain. The tradeoff is that GitHub's CDN may serve a slightly stale image for a few hours. With one data point per day that is invisible.

## How multi-host works

Each machine reads **only its own local logs** and writes to its own directory:

```
data/mac-a/2026-08-04.json     ← machine A only ever writes here
data/mac-b/2026-08-04.json     ← machine B only ever writes here
```

Two machines never write the same path, so there is no merge conflict to resolve and no cross-machine deduplication to get wrong. Merging is just addition at render time.

> [!IMPORTANT]
> This relies on the machines' log directories being **disjoint**. Do not sync `~/.claude` or `~/.codex` between machines via iCloud, Dropbox, Syncthing, or a restored backup — both machines would then see the same sessions and the totals would double. Because ccusage reports daily aggregates rather than session IDs, this repo cannot detect that from the data.

## How it stays correct

- **Idempotent.** Re-running for a day overwrites that day. Safe to trigger as often as you like.
- **Self-healing.** Every run re-collects a recall window (`clamp(days since last success + 2, 3, 21)`), so a laptop that was off for a week backfills itself on the next run.
- **Non-destructive for old days.** Beyond 7 days, values may only *grow*. If Claude Code has already cleaned up part of a day, a fresh read returns a smaller number — overwriting would silently corrupt a correct record. A missing day is visible; a shrunken one is not.
- **Version-stamped.** Every file records the ccusage version that produced it. ccusage v15 under-reported output tokens by ~38% relative to v20; if a future upstream change moves the numbers again, the step in the series will be traceable instead of mysterious.
- **No empty commits.** Nothing is committed when nothing changed. Costs are rounded on write, so float noise (~1e-13) doesn't manufacture a diff.

## Honest notes

**"Cost" is not money spent.** These are subscription plans. The dollar figure is what the same token usage would cost at published API rates — useful as a measure of value extracted from a subscription, misleading if read as a bill.

**ccusage is the source of truth.** This repo does not second-guess it. Worth knowing: on the machine this was built on, ccusage's Codex total differed by ~31% from an independent parse of the same rollout files. Which is right is unresolved. The Claude side reconciles exactly, field for field.

**Nothing identifying is recorded.** No project names, paths, branches, prompts, or real hostnames — only per-day token counts and model names, under an alias you choose. `config.json` is gitignored so the alias-to-machine mapping stays local.

## Layout

```
config.example.json          copy to config.json, set your host alias
.python-version              interpreter pin (uv)
scripts/
  run.sh                     entry point: uv if present, python3 otherwise
  collect.py                 ccusage → data/<host>/<date>.json
  render.py                  data/ → charts/*.svg + SUMMARY.md (--weeks N for weekly)
  install-launchd.sh         macOS scheduling (--uninstall to remove)
data/<host>/<date>.json      one file per host per day
charts/*.svg                 regenerated by CI on every data push
contexts/                    design decisions and the research behind them
```

`.github/workflows/render.yml` re-renders on every push that touches `data/`. Push-triggered rather than scheduled: GitHub's docs acknowledge that scheduled workflows can be delayed, dropped under load, and auto-disabled after 60 days of inactivity. None of that applies to a push trigger, and the charts update the moment data lands.

## Design notes

Everything non-obvious in here has a written reason — measured on real data, not assumed. See [`contexts/`](./contexts):

- [`decisions.md`](./contexts/decisions.md) — what was chosen and why
- [`data-sources.md`](./contexts/data-sources.md) — schemas, dedup, retention, the ccusage version story
- [`pipeline-and-scheduling.md`](./contexts/pipeline-and-scheduling.md) — layout, idempotency, git, launchd, chart constraints

## License

MIT
