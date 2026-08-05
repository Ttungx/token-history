#!/usr/bin/env python3
"""8-bit pixel style for the daily token chart.

One chart: charts/day/pixel-tokens.svg. Each daily column is a stack of
discrete square "pixels" on a fixed grid — every pixel is a fixed token
quantum (chosen from 1/2/5 x 10^n so the tallest day fits the grid), each
series rounds UP to whole pixels, and the footnote states the quantum, so
the quantization is honest. Claude Code fills the column bottom-up first,
Codex continues in the same grid (Tetris-style row packing), which keeps
the stacked-bar reading while the last row of a series may hold a single
square — the staircase feel is real data, not decoration.

Colors, text classes and both color modes come from render.THEME via
render.svg_start; the pixel look is pure geometry: shape-rendering:
crispEdges, integer coordinates, square corners, a stepped reveal
animation (steps() easing), and a terminal-cursor blink on the newest
pixel of an in-progress day. Deterministic: same data -> same bytes.

Targets Python 3.9, standard library only. Import with the repo's
scripts/ directory on sys.path (it does `import render`).
"""

import render

# ------------------------------------------------------------------ grid geometry

S = 8                 # pixel square edge
GAPX = 2              # gap between pixels, both directions
PITCH = S + GAPX      # 10px grid pitch
COLS_PER_BAR = 2      # each daily column is two pixels wide
BAR_W = COLS_PER_BAR * PITCH - GAPX          # 18px
MAX_ROWS = 24         # tallest column the grid allows
TICK_ROWS = 5         # one y tick every 5 rows = 10 quanta

PAD_L, PAD_R = 76, 28
PAD_T = 100
PLOT_H = MAX_ROWS * PITCH                    # 240
BASE_Y = PAD_T + PLOT_H                      # 340
H = BASE_Y + 56                              # 396
W = render.W                                 # 880

PIXEL_CSS = (
    ".px{shape-rendering:crispEdges}"
    ".tt{font-family:var(--fm);fill:var(--primary);font-weight:700;letter-spacing:3px}"
    ".sub{font-family:var(--fm);fill:var(--secondary);letter-spacing:1px}"
    ".ink{fill:var(--primary)}"
    ".gridp{stroke:var(--grid);stroke-width:1;shape-rendering:crispEdges;stroke-dasharray:4 4}"
    ".axp{stroke:var(--axis);stroke-width:2;shape-rendering:crispEdges}"
    # no `to` frame: the animation must settle at each column's own base
    # opacity, so `.wip{opacity:.5}` still fades an in-progress day after
    # the reveal finishes (an explicit to{opacity:1} would override it).
    ".col{animation:rise .5s steps(4,end) both}"
    "@keyframes rise{from{opacity:0;transform:translateY(14px)}}"
    ".blink{animation:blink 1.3s step-end infinite}"
    "@keyframes blink{0%,54%{opacity:1}55%,100%{opacity:.2}}"
)

# 7x6 pixel heart, drawn as tiny rects in primary ink (decorative, never a series hue)
HEART = (
    ".XX.XX.",
    "XXXXXXX",
    "XXXXXXX",
    ".XXXXX.",
    "..XXX..",
    "...X...",
)


def _ceil_div(a, b):
    return -(-a // b)


def _series_pixels(row, quantum):
    """Whole pixels per series, rounding up — a started pixel counts."""
    out = []
    for source, _ in render.SERIES:
        v = row[source]["total"]
        out.append((source, _ceil_div(v, quantum) if v > 0 else 0))
    return out


def _rows_needed(row, quantum):
    squares = sum(n for _, n in _series_pixels(row, quantum))
    return _ceil_div(squares, COLS_PER_BAR)


def _pick_quantum(rows):
    """Smallest nice quantum (1/2/5 x 10^n tokens) whose tallest column fits."""
    candidates = sorted(m * 10 ** e for e in range(5, 12) for m in (1, 2, 5))
    for q in candidates:
        if max([_rows_needed(r, q) for r in rows] + [0]) <= MAX_ROWS:
            return q
    return candidates[-1]


def _heart(add, x, y, px):
    add('<g class="ink px">')
    for r, line in enumerate(HEART):
        for c, ch in enumerate(line):
            if ch == "X":
                add('<rect x="{}" y="{}" width="{}" height="{}"/>'.format(
                    x + c * (px + 1), y + r * (px + 1), px, px))
    add('</g>')


def _pixel_legend(add, x, y):
    """Square-cornered take on render.draw_legend — same classes, same labels."""
    for source, label in render.SERIES:
        add('<rect class="px s-{}" x="{}" y="{}" width="8" height="8"/>'.format(source, x, y + 1))
        add('<text class="t2" x="{}" y="{}" font-size="12" font-family="var(--fm)">{}</text>'.format(
            x + 14, y + 9, render.esc(label)))
        x += 20 + len(label) * 8


def _build_pixel(rows, generated):
    n = len(rows)
    plot_w = W - PAD_L - PAD_R
    slot = plot_w / float(n)
    quantum = _pick_quantum(rows)

    totals = [sum(r[s]["total"] for s, _ in render.SERIES) for r in rows]
    grand = sum(totals)
    peak_idx = totals.index(max(totals)) if any(totals) else -1

    span = "{} - {}, {}".format(rows[0]["start"].strftime("%b %d").upper(),
                                rows[-1]["start"].strftime("%b %d").upper(),
                                rows[-1]["start"].year)
    title = "DAILY TOKENS"
    aria = "Daily token usage, 8-bit pixel chart, {}".format(span)
    subtitle = "{} / {} TOKENS OVER {} DAYS".format(span, render.compact_tokens(grand), n)

    out = render.svg_start(W, H, aria, PIXEL_CSS)
    add = out.append

    # ---- heading: chunky letter-spaced monospace fakes a bitmap face
    add('<text class="tt" x="28" y="36" font-size="17">{}</text>'.format(render.esc(title)))
    add('<text class="sub" x="28" y="57" font-size="11">{}</text>'.format(render.esc(subtitle)))
    _pixel_legend(add, 28, 67)
    _heart(add, W - PAD_R - 34, 24, 4)

    # ---- y grid: one axis, dashed "pixel" gridlines every TICK_ROWS rows
    for r in range(0, MAX_ROWS + 1, TICK_ROWS):
        y = BASE_Y - r * PITCH
        value = r * COLS_PER_BAR * quantum
        if r > 0:
            add('<line class="gridp" x1="{}" y1="{}" x2="{}" y2="{}"/>'.format(
                PAD_L, y, W - PAD_R, y))
        add('<text class="tm" x="{}" y="{}" font-size="10.5" text-anchor="end">{}</text>'.format(
            PAD_L - 10, y + 4, render.esc(render.compact_tokens(value))))
    add('<line class="axp" x1="{}" y1="{}" x2="{}" y2="{}"/>'.format(
        PAD_L, BASE_Y + 1, W - PAD_R, BASE_Y + 1))

    # ---- columns of pixels
    stride = max(1, -(-n // 9))
    col_rows = []
    for i, row in enumerate(rows):
        x0 = int(round(PAD_L + slot * (i + 0.5) - BAR_W / 2.0))
        wip = row["partial"]
        squares = []
        for source, count in _series_pixels(row, quantum):
            squares.extend([source] * count)
        col_rows.append(_ceil_div(len(squares), COLS_PER_BAR))

        if squares:
            add('<g class="col{}" style="animation-delay:{}ms">'.format(
                " wip" if wip else "", i * 18))
            for k, source in enumerate(squares):
                r, c = divmod(k, COLS_PER_BAR)
                x = x0 + c * PITCH
                y = BASE_Y - (r * PITCH + S)
                blink = " blink" if (wip and i == n - 1 and k == len(squares) - 1) else ""
                add('<rect class="px s-{}{}" x="{}" y="{}" width="{}" height="{}"/>'.format(
                    source, blink, x, y, S, S))
            add('</g>')

        # x labels, right-anchored stride so the newest day is always named
        if (n - 1 - i) % stride == 0:
            add('<text class="tm" x="{}" y="{}" font-size="10.5" text-anchor="middle" '
                'font-family="var(--fm)">{}</text>'.format(
                    int(round(PAD_L + slot * (i + 0.5))), BASE_Y + 19,
                    row["start"].strftime("%m/%d")))

    # ---- selective direct labels: peak + latest only (true totals, not pixels)
    label_idx = set()
    if peak_idx >= 0:
        label_idx.add(peak_idx)
    if n and totals[n - 1] > 0 and (peak_idx == n - 1 or n - 1 - peak_idx > 1):
        label_idx.add(n - 1)
    for idx in sorted(label_idx):
        cx = int(round(PAD_L + slot * (idx + 0.5)))
        clear = max(col_rows[max(0, idx - 1): idx + 1] or [0])   # clear the left neighbor too
        y = BASE_Y - max(col_rows[idx], clear) * PITCH - 6
        add('<text class="tn" x="{}" y="{}" font-size="11" font-weight="700" '
            'text-anchor="middle">{}</text>'.format(cx, y, render.esc(
                render.compact_tokens(totals[idx]))))

    foot = ("1 pixel = {} tokens; each series rounds up, so a started pixel counts. "
            "Faded column = day in progress (blinking cursor). Generated {}".format(
                render.compact_tokens(quantum), generated))
    add('<text class="tm" x="28" y="{}" font-size="10.5">{}</text>'.format(
        H - 14, render.esc(foot)))
    add("</svg>")
    return "\n".join(out)


def build_all(days, generated):
    """Returns [(relpath, svg_string)] for the 8-bit pixel style."""
    rows = render.bucket(days, render.DAYS)
    if not rows:
        return []
    return [("day/pixel-tokens.svg", _build_pixel(rows, generated))]
