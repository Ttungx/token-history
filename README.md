<div align="center">

# token-history

**A durable, self-updating record of how much AI coding I actually use —<br>persisted to git daily, charted a dozen ways, ready for a GitHub profile README.**

[![Render charts](https://github.com/keli-wen/token-history/actions/workflows/render.yml/badge.svg?branch=master)](https://github.com/keli-wen/token-history/actions/workflows/render.yml)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
![Python ≥3.9](https://img.shields.io/badge/python-%E2%89%A53.9-3776AB?logo=python&logoColor=white)
![dependencies: zero](https://img.shields.io/badge/dependencies-zero-brightgreen)
![license: MIT](https://img.shields.io/badge/license-MIT-blue)

<img src="./charts/badge/tokens-30d.svg" alt="tokens over the last 30 days"> <img src="./charts/badge/api-equiv-30d.svg" alt="API-equivalent value over the last 30 days"> <img src="./charts/badge/streak.svg" alt="active-day streak">

</div>

The repo keeps a day-by-day history; the two headline charts show the last 30 days, and every render also produces [a dozen other styles](#chart-gallery) across daily, weekly, and monthly granularity.

<img src="./charts/tokens.svg" width="880" alt="Daily token usage, stacked by source">

<img src="./charts/cost.svg" width="880" alt="Daily API-equivalent value, stacked by source">

📊 **[Full numbers → SUMMARY.md](./SUMMARY.md)** · day-by-day history in [`data/`](./data)

## Contents

- [Why this exists](#why-this-exists)
- [Quick start](#quick-start)
- [Chart gallery](#chart-gallery) — [daily](#daily) · [weekly](#weekly) · [monthly](#monthly) · [badges](#badges)
- [How multi-host works](#how-multi-host-works)
- [How it stays correct](#how-it-stays-correct)
- [Honest notes](#honest-notes)
- [Layout](#layout)
- [Design notes](#design-notes)
- [License](#license)

---

## Why this exists

Claude Code deletes session transcripts older than `cleanupPeriodDays` — **30 days by default**. Every tool that reports your usage, [`ccusage`](https://github.com/ccusage/ccusage) included, reads those transcripts. So your history isn't archived anywhere; it's on a rolling 30-day delete, and once a day falls off the edge no tool can recover it.

This repo snapshots the numbers into git before that happens. Three times a day, on each machine, idempotently.

It is **not** another usage parser. ccusage already does that job well and supports ~15 different coding CLIs. This adds the four things ccusage deliberately doesn't do:

| | |
|---|---|
| **Persist** | daily JSON in git, immune to local cleanup |
| **Merge** | several machines into one timeline |
| **Render** | a whole gallery of chart styles, regenerated automatically |
| **Serve** | a stable URL you reference once and never touch again |

## Quick start

**Prerequisites:** Node (for `npx ccusage`) and [uv](https://docs.astral.sh/uv/).

```bash
# 1. Install uv, if you don't have it yet
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS / Linux (or: brew install uv)

# 2. Clone and configure
git clone https://github.com/<you>/token-history && cd token-history
cp config.example.json config.json                # set "host" to an alias like mac-a

# 3. Set up the environment and run
uv sync                                           # one-time: provisions the pinned Python + .venv
./scripts/run.sh collect --all                    # backfill everything ccusage still has
./scripts/run.sh render                           # build every chart locally
```

**How uv is used here.** This is a standard uv project: `pyproject.toml` declares the (empty — everything is stdlib) dependency set, `.python-version` pins the interpreter, and `uv.lock` is committed. `uv sync` materialises that into `.venv`, and `uv run` re-syncs automatically whenever the lockfile changes — so your terminal, the launchd job at 00:30, and CI all run the exact same Python instead of whatever `python3` happens to be ambient. `run.sh` is a thin wrapper over the same thing (it survives launchd's minimal `PATH`); calling uv directly works too:

```bash
uv run scripts/collect.py --all
uv run scripts/render.py
```

No uv at all? `run.sh` falls back to plain `python3` (≥ 3.9) automatically — the scripts have zero dependencies, so the fallback is a real path, not a courtesy.

Then schedule it (macOS):

```bash
./scripts/install-launchd.sh           # 00:30 / 12:00 / 21:00 + every login
```

Not on macOS, or prefer a different trigger? The collector is fully self-contained, idempotent, and backfills its own gaps — so **anything** that calls it periodically works: cron, a systemd timer, a line in your shell profile, or running it by hand. The scheduler is not load-bearing.

To show the charts elsewhere, reference the raw URLs:

```markdown
![tokens](https://raw.githubusercontent.com/<you>/token-history/master/charts/tokens.svg)
![cost](https://raw.githubusercontent.com/<you>/token-history/master/charts/cost.svg)
```

The URL is stable — no cache-busting query, no write access to your profile repo, nothing to maintain. The tradeoff is that GitHub's CDN may serve a slightly stale image for a few hours. With one data point per day that is invisible.

## Chart gallery

Every run renders **every** style below — the same data, eleven ways. This section is deliberately fully expanded: it doubles as a catalog to pick from and as a live test of how each SVG actually behaves inside GitHub's README renderer (light/dark via `prefers-color-scheme`, CSS load animations, font fallbacks). In practice you'd embed just one or two in your own profile README:

```markdown
![usage](https://raw.githubusercontent.com/<you>/token-history/master/charts/day/card.svg)
```

`charts/tokens.svg` and `charts/cost.svg` remain stable aliases of the daily bars, so existing embeds never break. Colors and type follow Anthropic's palette (orange = Claude Code, blue = Codex), tuned per mode to pass a color-vision-deficiency check.

### Daily

**`charts/day/bar-tokens.svg`** — the headline chart (alias: `charts/tokens.svg`)

<img src="./charts/day/bar-tokens.svg" width="880" alt="Daily token usage, stacked by source">

**`charts/day/bar-cost.svg`** — same bars, API-equivalent dollars (alias: `charts/cost.svg`)

<img src="./charts/day/bar-cost.svg" width="880" alt="Daily API-equivalent value, stacked by source">

**`charts/day/calendar-tokens.svg`** — contribution-style calendar heatmap

<img src="./charts/day/calendar-tokens.svg" alt="Daily token calendar: one cell per day, darker means more tokens">

**`charts/day/area-tokens.svg`** — smoothed stacked area with an animated reveal

<img src="./charts/day/area-tokens.svg" width="880" alt="Daily token flow: stacked area of Claude and Codex tokens">

**`charts/day/card.svg`** — hero-number stat card for the last 30 days

<img src="./charts/day/card.svg" width="880" alt="30-day stat card: total tokens, API-equivalent value, peak day, daily average, and the Claude/Codex split">

**`charts/day/pixel-tokens.svg`** — 8-bit pixel bars: every square is 10M tokens on a crisp retro grid, with a blinking cursor on the day still in progress

<img src="./charts/day/pixel-tokens.svg" width="880" alt="Pixel-art daily token bars: stacks of squares, one square per 10M tokens">

**`charts/day/terminal-tokens.svg`** — the last 30 days as a terminal session: an htop-style bar per day, a CLI-style `TOTAL` sign-off, and a blinking cursor

<img src="./charts/day/terminal-tokens.svg" width="880" alt="Terminal-style chart: a shell window with one ASCII bar per day, stacked Claude/Codex block glyphs">

**`charts/day/sketch-tokens.svg`** — an xkcd-style hand-drawn take: two wobbly ink lines, hand-lettered labels, and a scribbled circle around the day the agents took over

<img src="./charts/day/sketch-tokens.svg" width="880" alt="Hand-drawn xkcd-style chart: wobbly Claude and Codex lines with a circled annotation on the peak day">

### Weekly

**`charts/week/bar-tokens.svg`** — weekly bars

<img src="./charts/week/bar-tokens.svg" width="880" alt="Weekly token usage, stacked by source">

**`charts/week/bar-cost.svg`** — weekly API-equivalent dollars

<img src="./charts/week/bar-cost.svg" width="880" alt="Weekly API-equivalent value, stacked by source">

**`charts/week/ledger-tokens.svg`** — editorial ledger, newest week on top

<img src="./charts/week/ledger-tokens.svg" width="880" alt="Weekly ledger: one row per week with a stacked horizontal bar and the total">

### Monthly

**`charts/month/bar-tokens.svg`** — monthly bars

<img src="./charts/month/bar-tokens.svg" width="880" alt="Monthly token usage, stacked by source">

**`charts/month/bar-cost.svg`** — monthly API-equivalent dollars

<img src="./charts/month/bar-cost.svg" width="880" alt="Monthly API-equivalent value, stacked by source">

**`charts/month/calendar-tokens.svg`** — a calendar page for the current month

<img src="./charts/month/calendar-tokens.svg" width="880" alt="Calendar page for the current month, each day shaded and labelled by its token total">

### Badges

**`charts/badge/*.svg`** — live shields.io-style stats, rendered from the same data. Inline-sized: drop any of them on a single line of your profile README.

<img src="./charts/badge/tokens-today.svg" alt="tokens today"> <img src="./charts/badge/tokens-30d.svg" alt="tokens over the last 30 days"> <img src="./charts/badge/api-equiv-30d.svg" alt="API-equivalent value over the last 30 days"> <img src="./charts/badge/daily-avg.svg" alt="daily average tokens"> <img src="./charts/badge/split-30d.svg" alt="Claude versus Codex share"> <img src="./charts/badge/streak.svg" alt="active-day streak">

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
pyproject.toml, uv.lock      uv project: zero dependencies, locked anyway
.python-version              interpreter pin (3.12, provisioned by uv)
scripts/
  run.sh                     entry point: uv if present, python3 otherwise
  collect.py                 ccusage → data/<host>/<date>.json
  render.py                  data/ → charts (every style) + SUMMARY.md
  install-launchd.sh         macOS scheduling (--uninstall to remove)
data/<host>/<date>.json      one file per host per day
charts/tokens.svg, cost.svg  the two headline charts (stable URLs)
charts/{day,week,month}/     the style gallery, all regenerated by CI on every data push
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
