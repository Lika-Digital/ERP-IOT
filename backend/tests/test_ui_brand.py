"""UI brand — design tokens and the rules a redesign must not lose.

TC-UIB-01  every text/background pair in the tokens meets WCAG AA (4.5:1), both themes
TC-UIR-01  status is icon + word + colour: one <Status> component, all three props
           required, and no raw palette colour class in a redesigned screen
TC-UIR-04  the 360 px rule is checked in the browser (scripts/browser_check.py)

Source scans, like SIM-15: the mechanism is asserted, not a screenshot.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "frontend" / "src"
_TOKENS = _SRC / "theme" / "tokens.css"

# Screens moved onto the tokens. A screen joins this list in the commit that
# redesigns it; at the end of the redesign it is every file under pages/.
REDESIGNED = [
    "components/layout/Layout.tsx",
    "components/auth/AuthCard.tsx",
    "components/auth/MfaSteps.tsx",
    "components/ui/Status.tsx",
    "pages/Login.tsx",
    "pages/Berths.tsx",
    "pages/Security.tsx",
]

# (text, background) pairs that appear on screen
PAIRS = [
    ("fg", "canvas"), ("fg", "surface"), ("fg", "surface-2"),
    ("fg-muted", "canvas"), ("fg-muted", "surface"), ("fg-muted", "surface-2"),
    ("link", "surface"), ("link", "canvas"),
    ("accent-ink", "accent"), ("accent-ink", "accent-hover"),
    ("sidebar-fg", "sidebar"), ("sidebar-muted", "sidebar"), ("sidebar-fg", "sidebar-2"),
    ("accent", "sidebar"),
    ("danger-ink", "danger"),
] + [(f"st-{c}-fg", f"st-{c}-bg") for c in ("green", "yellow", "orange", "red", "blue", "grey")]


def _themes() -> dict[str, dict[str, tuple[int, int, int]]]:
    css = _TOKENS.read_text(encoding="utf-8")
    out = {}
    for name, selector in (("light", r":root,\s*:root\.light\s*\{"), ("dark", r":root\.dark\s*\{")):
        m = re.search(selector + r"(.*?)\n\}", css, re.S)
        assert m, f"no {name} block in tokens.css"
        out[name] = {k: tuple(int(x) for x in v.split())
                     for k, v in re.findall(r"--([\w-]+):\s*(\d+ \d+ \d+);", m.group(1))}
    return out


def _lum(rgb):
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_uib_01_every_token_pair_meets_wcag_aa(theme):
    t = _themes()[theme]
    low = [f"{fg} on {bg}: {contrast(t[fg], t[bg]):.2f}" for fg, bg in PAIRS
           if contrast(t[fg], t[bg]) < 4.5]
    assert low == []


def test_uib_01_both_themes_define_the_same_tokens():
    t = _themes()
    assert set(t["light"]) == set(t["dark"])


def test_uib_01_the_checker_is_right():
    # WCAG reference values: black/white 21:1, #777 on white ~4.48 (just fails AA)
    assert round(contrast((0, 0, 0), (255, 255, 255)), 1) == 21.0
    assert contrast((119, 119, 119), (255, 255, 255)) < 4.5


def test_uir_01_status_takes_icon_word_and_tone_all_required():
    src = (_SRC / "components" / "ui" / "Status.tsx").read_text(encoding="utf-8")
    props = re.search(r"interface StatusProps \{(.*?)\}", src, re.S)
    assert props, "Status.tsx must declare StatusProps"
    for name in ("tone", "icon", "word"):
        assert re.search(rf"^\s*{name}:", props.group(1), re.M), f"{name} must be a required prop"
        assert not re.search(rf"^\s*{name}\?:", props.group(1), re.M)


# Tailwind palette colours. A redesigned screen says what it means (bg-surface,
# text-fg-muted, <Status tone=...>), never which hue it happens to be.
_RAW = re.compile(
    r"\b(?:bg|text|border|ring|from|to|via|divide|outline|fill|stroke)-"
    r"(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|"
    r"sky|blue|indigo|violet|purple|fuchsia|pink|rose|brand|marina)-\d{2,3}\b")


@pytest.mark.parametrize("rel", REDESIGNED)
def test_uir_01_no_raw_palette_colour_in_a_redesigned_screen(rel):
    text = (_SRC / rel).read_text(encoding="utf-8")
    assert _RAW.findall(text) == []


@pytest.mark.parametrize("rel", [r for r in REDESIGNED if r.startswith("pages/")])
def test_uir_01_status_in_a_redesigned_screen_goes_through_status(rel):
    text = (_SRC / rel).read_text(encoding="utf-8")
    assert "badge-" not in text, "a coloured badge is status without icon and word"


def test_uib_02_no_external_font_or_asset_request():
    html = (_REPO / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in html and "fonts.gstatic.com" not in html
    assert 'href="/lika-mark.svg"' in html
