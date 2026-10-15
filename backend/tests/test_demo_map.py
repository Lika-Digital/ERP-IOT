"""D28 — the demo marina's map is drawn once and holds exactly the 150 berths (spec §6.1)."""
import re
import sys
from pathlib import Path

from simulator import demo_world as w

REPO = Path(__file__).resolve().parents[2]
SVG = REPO / "frontend" / "public" / "maps" / "demo-marina.svg"


def test_every_berth_has_exactly_one_element_and_nothing_else_claims_to_be_one():
    ids = re.findall(r'id="(berth-[^"]+)"', SVG.read_text(encoding="utf-8"))
    assert sorted(ids) == sorted(b.svg_id for b in w.berths())
    assert len(ids) == len(set(ids)) == 150


def test_the_file_in_the_repo_is_what_the_generator_draws():
    sys.path.insert(0, str(REPO / "scripts"))
    import demo_map
    assert SVG.read_text(encoding="utf-8") == demo_map.svg()


def test_the_picture_is_not_shipped_with_the_app():
    # 2.8 MB on every dashboard load; the shapes say the same (scripts/demo_map.py)
    assert not list((REPO / "frontend").rglob("marina-demo.png"))
    assert "<image" not in SVG.read_text(encoding="utf-8")
