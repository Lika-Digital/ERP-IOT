"""Draw the demo marina's 2D map ONCE (D28, spec §6.1, §6.11).

    python scripts/demo_map.py            -> frontend/public/maps/demo-marina.svg
    python scripts/demo_map.py --check    -> also an overlay on docs/ui/marina-demo.png

The geometry is measured on docs/ui/marina-demo.png (1536 x 1024) and kept in that
coordinate space: pontoons A–E from the north walkway southwards, berths on both
sides (odd west, even east, from the root), the north and south quays west to east,
the east quay north to south. The app never changes this geometry — it only sets
a class on each `berth-<id>` element (§6.1). The picture itself is NOT shipped:
2.8 MB on every dashboard load buys nothing the shapes do not say.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from simulator import demo_world as w  # noqa: E402

OUT = ROOT / "frontend" / "public" / "maps" / "demo-marina.svg"
W, H = 1536, 1024

# pontoon: x of the walkway, boat length in px (20 / 15 / 10 m)
PONTOONS = {"A": (287, 74), "B": (485, 58), "C": (676, 58), "D": (862, 40), "E": (1036, 40)}
ROW0, ROW_STEP, ROWS = 320, 38, 10          # first berth row (root), step, rows per side
WALK = 12                                   # walkway width
BERTH_H = 26                                # across the boat


def _rect(bid, x, y, w_, h_):
    return (f'  <rect id="berth-{bid}" class="berth" data-berth="{bid}" x="{x:.0f}" y="{y:.0f}" '
            f'width="{w_:.0f}" height="{h_:.0f}" rx="4"/>')


# v21 (T2): the number of the first berth of each pier, inside it — part of the drawing,
# so the app still only sets classes. No <title>: the app's tooltip says more.
def _num(bid, x, y, w_, h_):
    cx, cy = x + w_ / 2, y + h_ / 2
    rot = f' transform="rotate(-90 {cx:.0f} {cy:.0f})"' if h_ > w_ else ""
    return (f'  <text class="num" x="{cx:.0f}" y="{cy:.0f}" text-anchor="middle" '
            f'dominant-baseline="central"{rot}>{bid}</text>')


def berth_shapes(numbers: list | None = None) -> list[str]:
    out = []
    first = {w.berth_id(z, i) for z in PONTOONS for i in (1, 2)} | {
        w.berth_id(q, 1) for q in ("QN", "QE", "QS")}

    def rect(bid, x, y, w_, h_):
        out.append(_rect(bid, x, y, w_, h_))
        if numbers is not None and bid in first:
            numbers.append(_num(bid, x, y, w_, h_))
    for z, (cx, length) in PONTOONS.items():
        for i in range(1, 21):
            row, west = (i - 1) // 2, i % 2 == 1
            y = ROW0 + row * ROW_STEP - BERTH_H / 2
            x = cx - WALK / 2 - 4 - length if west else cx + WALK / 2 + 4
            rect(w.berth_id(z, i), x, y, length, BERTH_H)
    # north quay: 25 berths, bows to the quay, west to east
    for i in range(1, 26):
        x = 289 + (i - 1) * (1032 - 289) / 24
        rect(w.berth_id("QN", i), x - 12, 140, 24, 58)
    # east quay: 15 berths, along the pier, north to south
    for i in range(1, 16):
        y = 255 + (i - 1) * (655 - 255) / 14
        rect(w.berth_id("QE", i), 1136, y - 10, 46, 20)
    # south quay: 10 berths, bows to the quay, west to east
    for i in range(1, 11):
        x = 375 + (i - 1) * (735 - 375) / 9
        rect(w.berth_id("QS", i), x - 12, 780, 24, 50)
    return out


def structures() -> list[str]:
    s = ['  <rect class="land" x="0" y="0" width="140" height="1024"/>',
         '  <path class="land" d="M140 0 H1210 V120 H240 V230 H140 Z"/>',             # north shore
         '  <rect class="walk" x="200" y="118" width="1010" height="16" rx="3"/>',      # north quay
         '  <rect class="walk" x="140" y="282" width="925" height="12" rx="3"/>',       # pontoon root
         '  <path class="land" d="M140 770 H290 V845 H780 V800 H1215 V870 H140 Z"/>',  # south shore
         '  <rect class="walk" x="290" y="832" width="490" height="14" rx="3"/>',       # south quay
         '  <path class="walk" d="M1185 200 H1200 V420 L1250 470 V720 H1222 V480 L1185 440 Z"/>']
    for x in (262, 505, 655, 798):                                                   # bridges
        s.append(f'  <rect class="walk" x="{x - 5}" y="132" width="10" height="152"/>')
    for z, (cx, _len) in PONTOONS.items():
        s.append(f'  <rect class="walk" x="{cx - WALK / 2:.0f}" y="282" width="{WALK}" '
                 f'height="{ROW0 + (ROWS - 1) * ROW_STEP + 30 - 282}" rx="3"/>')
        s.append(f'  <text class="label" x="{cx}" y="268" text-anchor="middle">{z}</text>')
    s += ['  <text class="label" x="660" y="112" text-anchor="middle">North quay</text>',
          '  <text class="label" x="540" y="870" text-anchor="middle">South quay</text>',
          '  <text class="label" x="1272" y="460" transform="rotate(90 1272 460)" '
          'text-anchor="middle">East quay</text>']
    return s


def svg(background: str | None = None) -> str:
    bg = (f'  <image href="{background}" x="0" y="0" width="{W}" height="{H}" opacity="0.55"/>'
          if background else '  <rect class="water" x="0" y="0" width="1536" height="1024"/>')
    head = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
            f'data-map="demo-marina" role="img" aria-label="Demo Marina — 150 berths">')
    note = ("<!-- Generated by scripts/demo_map.py from docs/ui/marina-demo.png. Do not edit: "
            "the app only sets the class of each berth-<id>. -->")
    # the app's theme sets the variables (frontend/src/theme/tokens.css); the
    # fallbacks keep the file readable on its own
    style = ("  <style>.water{fill:var(--map-water,#d7e6ee)}.land{fill:var(--map-land,#eceae4)}"
             ".walk{fill:var(--map-walk,#c9b79a)}.label{font:600 22px system-ui,sans-serif;"
             "fill:var(--map-label,#2b2a29)}.berth{fill:var(--map-berth,#ffffff);"
             "stroke:var(--map-berth-line,#8a8f94);stroke-width:1.5}"
             ".num{font:700 12px system-ui,sans-serif;fill:var(--map-label,#2b2a29);"
             "pointer-events:none}</style>")
    numbers: list = []
    shapes = berth_shapes(numbers)
    body = ([style, bg] + ([] if background else structures()) +
            ['  <g class="berths">'] + shapes + ['  </g>', '  <g class="nums" aria-hidden="true">'] +
            numbers + ['  </g>'])
    return "\n".join([note, head, *body, "</svg>", ""])


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--check", metavar="DIR", help="also write an overlay on the picture here")
    a = p.parse_args(argv)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(svg(), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    if a.check:
        d = Path(a.check)
        d.mkdir(parents=True, exist_ok=True)
        (d / "overlay.svg").write_text(svg(background=(ROOT / "docs/ui/marina-demo.png").as_uri()),
                                       encoding="utf-8")
        print(f"wrote {d / 'overlay.svg'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
