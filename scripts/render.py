#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Render the usage charts as dependency-free SVG.

Two charts, never one with two y-scales:
  charts/tokens.svg  — total tokens per day, stacked by source
  charts/cost.svg    — API-equivalent USD per day, stacked by source

Defaults to 30 daily columns; `--weeks N` switches to weekly buckets.

Both are static SVG with an embedded `prefers-color-scheme` style block, so a
single file works on GitHub in light and dark. Note the limit: that media query
follows the OS/browser setting, NOT GitHub's own theme toggle — an <img>-embedded
SVG cannot see the host page's theme. This is the best available mechanism.

Targets Python 3.9. Standard library only (must run in GitHub Actions and in
anyone's fork without a package install).
"""

import argparse
import datetime as dt
import glob
import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
CHART_DIR = os.path.join(REPO_ROOT, "charts")

DAYS = 30           # default window: one month of daily columns
WEEKS = 16          # only used with --weeks
W = 880
PAD_L, PAD_R, PAD_T, PAD_B = 76, 28, 92, 52
PLOT_H = 224
H = PAD_T + PLOT_H + PAD_B
BAR_MAX = 24          # marks/anatomy: cap bar thickness, let the leftover be air
GAP = 2               # the surface gap that separates stacked segments
CAP_R = 4             # rounded data-end; square at the baseline

# Categorical slots 1 and 2. Validated in both modes with
# scripts/validate_palette.js — all six checks PASS (worst CVD dE 24.7 light /
# 26.8 dark against a >=8 target). Do not substitute without re-validating.
THEME = {
    "light": {
        "surface": "#fcfcfb", "primary": "#0b0b0b", "secondary": "#52514e",
        "muted": "#898781", "grid": "#e1e0d9", "axis": "#c3c2b7",
        "claude": "#2a78d6", "codex": "#eb6834",
    },
    "dark": {
        "surface": "#1a1a19", "primary": "#ffffff", "secondary": "#c3c2b7",
        "muted": "#898781", "grid": "#2c2c2a", "axis": "#383835",
        "claude": "#3987e5", "codex": "#d95926",
    },
}
SERIES = [("claude", "Claude Code"), ("codex", "Codex")]
FONT = 'system-ui,-apple-system,"Segoe UI",Roboto,sans-serif'


# ------------------------------------------------------------------- load data


def load_days():
    """{date: {'claude': {...}, 'codex': {...}, 'partial': bool}} merged over hosts."""
    days = {}
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*", "2*.json"))):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                rec = json.load(fh)
        except (ValueError, OSError):
            continue
        date = rec.get("date")
        if not date:
            continue
        slot = days.setdefault(date, {"partial": False})
        if rec.get("status") == "partial":
            slot["partial"] = True
        for source, payload in (rec.get("sources") or {}).items():
            agg = slot.setdefault(source, {"total": 0, "costUSD": 0.0})
            # Hosts are disjoint writers for the same date, so summing is the merge.
            agg["total"] += payload.get("total") or 0
            agg["costUSD"] += payload.get("costUSD") or 0.0
    return days


def week_start(date):
    """Monday of the ISO week containing `date`."""
    return date - dt.timedelta(days=date.weekday())


def bucket(days, span, weekly=False):
    """Fold per-day records into `span` consecutive buckets ending on the last
    day with data.

    Daily is the default. Over a month-long window weekly aggregation leaves
    only four or five fat columns, which reads worse than thirty thin ones and
    hides the day-to-day rhythm that is the point of keeping the record.
    """
    if not days:
        return []
    last = max(dt.date.fromisoformat(d) for d in days)
    key = week_start if weekly else (lambda d: d)
    step = dt.timedelta(weeks=1) if weekly else dt.timedelta(days=1)
    first = key(last) - step * (span - 1)
    buckets = {}
    for offset in range(span):
        start = first + step * offset
        buckets[start] = {"start": start, "partial": False,
                          "claude": {"total": 0, "costUSD": 0.0},
                          "codex": {"total": 0, "costUSD": 0.0}}
    for date_str, payload in days.items():
        start = key(dt.date.fromisoformat(date_str))
        if start not in buckets:
            continue
        row = buckets[start]
        if payload.get("partial"):
            row["partial"] = True
        for source, _ in SERIES:
            if source in payload:
                row[source]["total"] += payload[source]["total"]
                row[source]["costUSD"] += payload[source]["costUSD"]
    return [buckets[k] for k in sorted(buckets)]


# --------------------------------------------------------------------- helpers


def compact_tokens(value):
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if value >= limit:
            scaled = value / limit
            return "{:.0f}{}".format(scaled, suffix) if scaled >= 10 else "{:.1f}{}".format(scaled, suffix)
    return "{:,.0f}".format(value)


def compact_cost(value):
    if value >= 100 or value == 0:
        return "${:,.0f}".format(value)
    return "${:,.1f}".format(value)


def nice_ticks(peak):
    """Clean tick steps (1/2/2.5/5 x 10^n), choosing the division that wastes the
    least headroom. Trying only one tick count leaves charts with a half-empty
    plot (peak $2,223 under a $4,000 axis)."""
    if peak <= 0:
        return [0, 1]
    best = None
    for count in (4, 5, 6):
        raw = peak / float(count)
        exp = 0
        scaled = raw
        while scaled >= 10:
            scaled /= 10.0
            exp += 1
        while scaled < 1:
            scaled *= 10.0
            exp -= 1
        magnitude = 10.0 ** exp
        for mult in (1, 2, 2.5, 5, 10):
            step = mult * magnitude
            if step * count >= peak:
                break
        top = step * count
        if best is None or top < best[0]:
            best = (top, count, step)
    _, count, step = best
    return [step * i for i in range(count + 1)]


def esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def cap_path(x, y, w, h, r):
    """Column with a rounded data-end and a square baseline."""
    r = max(0.0, min(float(r), w / 2.0, h))
    if r <= 0:
        return 'M{x:.1f},{y:.1f} h{w:.1f} v{h:.1f} h-{w:.1f} Z'.format(x=x, y=y, w=w, h=h)
    return (
        'M{x:.1f},{yb:.1f} V{yt:.1f} a{r:.1f},{r:.1f} 0 0 1 {r:.1f},-{r:.1f} '
        'h{inner:.1f} a{r:.1f},{r:.1f} 0 0 1 {r:.1f},{r:.1f} V{yb:.1f} Z'
    ).format(x=x, yb=y + h, yt=y + r, r=r, inner=w - 2 * r)


# ---------------------------------------------------------------------- render


def build_svg(rows, metric, title, subtitle, footnote, fmt):
    peak = max([sum(r[s][metric] for s, _ in SERIES) for r in rows] + [0])
    ticks = nice_ticks(peak)
    top = ticks[-1] or 1
    plot_w = W - PAD_L - PAD_R
    slot = plot_w / float(len(rows))
    bar_w = min(BAR_MAX, slot * 0.62)
    # aim for <= 9 x-axis labels whatever the bucket count
    stride = max(1, -(-len(rows) // 9))

    def y_of(value):
        return PAD_T + PLOT_H - (value / float(top)) * PLOT_H

    out = []
    add = out.append

    add('<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" '
        'viewBox="0 0 {} {}" role="img" aria-label="{}">'.format(W, H, W, H, esc(title)))

    light, dark = THEME["light"], THEME["dark"]
    css_vars = lambda t: " ".join("--{}:{};".format(k, v) for k, v in t.items())
    add("<style>")
    add("svg{{--f:{};{}}}".format(FONT, css_vars(light)))
    add("@media (prefers-color-scheme: dark){{svg{{{}}}}}".format(css_vars(dark)))
    add(".bg{fill:var(--surface)}")
    add(".grid{stroke:var(--grid);stroke-width:1;shape-rendering:crispEdges}")
    add(".axis{stroke:var(--axis);stroke-width:1;shape-rendering:crispEdges}")
    add(".t{font-family:var(--f);fill:var(--primary)}")
    add(".t2{font-family:var(--f);fill:var(--secondary)}")
    add(".tm{font-family:var(--f);fill:var(--muted);font-variant-numeric:tabular-nums}")
    add(".s-claude{fill:var(--claude)}.s-codex{fill:var(--codex)}")
    add(".wip{opacity:.5}")
    add("</style>")

    add('<rect class="bg" width="{}" height="{}"/>'.format(W, H))

    # ---- heading
    add('<text class="t" x="{}" y="30" font-size="17" font-weight="600">{}</text>'.format(PAD_L - 48, esc(title)))
    add('<text class="t2" x="{}" y="50" font-size="12">{}</text>'.format(PAD_L - 48, esc(subtitle)))

    # ---- legend (always present for >= 2 series; identity is never color-alone).
    # "in progress" is deliberately NOT a legend entry: it is a state both series
    # can be in, and a third swatch reads as a third category.
    lx = PAD_L - 48
    for source, label in SERIES:
        add('<rect class="s-{}" x="{}" y="62" width="10" height="10" rx="2"/>'.format(source, lx))
        add('<text class="t2" x="{}" y="71" font-size="12">{}</text>'.format(lx + 16, esc(label)))
        lx += 22 + len(label) * 7

    # ---- gridlines + y ticks (no gridline at zero — the baseline already draws it)
    for tick in ticks:
        y = y_of(tick)
        if tick > 0:
            add('<line class="grid" x1="{}" y1="{:.1f}" x2="{}" y2="{:.1f}"/>'.format(PAD_L, y, W - PAD_R, y))
        add('<text class="tm" x="{}" y="{:.1f}" font-size="11" text-anchor="end">{}</text>'.format(
            PAD_L - 10, y + 4, esc(fmt(tick))))
    base_y = y_of(0)
    add('<line class="axis" x1="{}" y1="{:.1f}" x2="{}" y2="{:.1f}"/>'.format(PAD_L, base_y, W - PAD_R, base_y))

    # ---- columns
    totals = [sum(r[s][metric] for s, _ in SERIES) for r in rows]
    peak_idx = totals.index(max(totals)) if any(totals) else -1
    for i, row in enumerate(rows):
        cx = PAD_L + slot * (i + 0.5)
        x = cx - bar_w / 2.0
        stack = 0.0
        drawn = [(s, row[s][metric]) for s, _ in SERIES if row[s][metric] > 0]
        for j, (source, value) in enumerate(drawn):
            y_top = y_of(stack + value)
            y_bot = y_of(stack)
            h = y_bot - y_top
            is_top = (j == len(drawn) - 1)
            if not is_top:
                h = max(0.0, h - GAP)          # surface gap does the separating
                y_top = y_bot - h
            cls = "s-{}{}".format(source, " wip" if row["partial"] else "")
            add('<path class="{}" d="{}"/>'.format(cls, cap_path(x, y_top, bar_w, h, CAP_R if is_top else 0)))
            stack += value

        # x labels: thin them out so the band never crowds, and anchor the
        # sequence to the right so the most recent bucket is always labelled.
        if (len(rows) - 1 - i) % stride == 0:
            add('<text class="tm" x="{:.1f}" y="{}" font-size="10.5" text-anchor="middle">{}</text>'.format(
                cx, PAD_T + PLOT_H + 20, row["start"].strftime("%m/%d")))

    # ---- selective direct labels: the peak and the most recent bucket only
    for idx in {peak_idx, len(rows) - 1}:
        if idx < 0 or not totals[idx]:
            continue
        cx = PAD_L + slot * (idx + 0.5)
        add('<text class="t" x="{:.1f}" y="{:.1f}" font-size="11.5" font-weight="600" '
            'text-anchor="middle">{}</text>'.format(cx, y_of(totals[idx]) - 8, esc(fmt(totals[idx]))))

    add('<text class="tm" x="{}" y="{}" font-size="10.5">{}</text>'.format(
        PAD_L - 48, H - 14, esc(footnote)))
    add("</svg>")
    return "\n".join(out)


def write_summary(path, rows, days):
    """The charts' table twin.

    A chart must never be the only way to read a value — colour-blind readers,
    screen readers, and anyone on a text-only view need the numbers themselves.
    """
    lines = [
        "# Summary",
        "",
        "Auto-generated by `scripts/render.py`. The table twin of the charts — "
        "every plotted value is readable here without relying on colour.",
        "",
        "## By bucket",
        "",
        "| Starting | Claude tokens | Codex tokens | Total tokens | Claude $ | Codex $ | Total $ |",
        "|---|--:|--:|--:|--:|--:|--:|",
    ]
    for row in reversed(rows):
        ct, xt = row["claude"]["total"], row["codex"]["total"]
        cc, xc = row["claude"]["costUSD"], row["codex"]["costUSD"]
        mark = " *" if row["partial"] else ""
        lines.append("| {}{} | {:,} | {:,} | {:,} | ${:,.2f} | ${:,.2f} | ${:,.2f} |".format(
            row["start"].isoformat(), mark, ct, xt, ct + xt, cc, xc, cc + xc))
    lines += ["", "`*` still in progress.", "", "## Last 30 days", "",
              "| Date | Claude tokens | Codex tokens | Claude $ | Codex $ |",
              "|---|--:|--:|--:|--:|"]
    for date_str in sorted(days, reverse=True)[:30]:
        day = days[date_str]
        claude = day.get("claude") or {"total": 0, "costUSD": 0.0}
        codex = day.get("codex") or {"total": 0, "costUSD": 0.0}
        mark = " *" if day.get("partial") else ""
        lines.append("| {}{} | {:,} | {:,} | ${:,.2f} | ${:,.2f} |".format(
            date_str, mark, claude["total"], codex["total"], claude["costUSD"], codex["costUSD"]))
    lines += ["", "Full day-by-day history lives in `data/<host>/<date>.json`.", ""]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description="Render the usage charts.")
    ap.add_argument("--days", type=int, default=DAYS, help="daily buckets (default)")
    ap.add_argument("--weeks", type=int, help="switch to weekly buckets")
    ap.add_argument("--out", default=CHART_DIR)
    args = ap.parse_args()

    days = load_days()
    if not days:
        print("no data under {}, nothing to render".format(DATA_DIR))
        return

    weekly = args.weeks is not None
    rows = bucket(days, args.weeks if weekly else args.days, weekly=weekly)
    last_day = rows[-1]["start"] + dt.timedelta(days=6 if weekly else 0)
    span = "{} – {}".format(rows[0]["start"].strftime("%b %d, %Y"), last_day.strftime("%b %d, %Y"))
    unit = "weeks" if weekly else "days"
    period = "Weekly" if weekly else "Daily"
    current = "week" if weekly else "day"
    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    os.makedirs(args.out, exist_ok=True)

    grand_tokens = sum(sum(r[s]["total"] for s, _ in SERIES) for r in rows)
    grand_cost = sum(sum(r[s]["costUSD"] for s, _ in SERIES) for r in rows)

    charts = [
        ("tokens.svg", "total", "{} token usage".format(period),
         "{} · {} tokens over {} {}".format(span, compact_tokens(grand_tokens), len(rows), unit),
         "Total tokens = input + output + cache creation + cache read. "
         "Current {} in progress, drawn faded. Generated {}".format(current, generated),
         compact_tokens),
        ("cost.svg", "costUSD", "{} API-equivalent value".format(period),
         "{} · {} over {} {}".format(span, compact_cost(grand_cost), len(rows), unit),
         "Not money spent — subscription plans priced at published API rates. "
         "Current {} in progress, drawn faded. Generated {}".format(current, generated),
         compact_cost),
    ]
    for name, metric, title, subtitle, footnote, fmt in charts:
        path = os.path.join(args.out, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(build_svg(rows, metric, title, subtitle, footnote, fmt) + "\n")
        print("wrote {}".format(os.path.relpath(path, REPO_ROOT)))

    summary = os.path.join(REPO_ROOT, "SUMMARY.md")
    write_summary(summary, rows, days)
    print("wrote {}".format(os.path.relpath(summary, REPO_ROOT)))


if __name__ == "__main__":
    main()
