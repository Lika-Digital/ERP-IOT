"""D30 — phase 1: pictures and video stay on the cabinet (spec §6.12).

The ERP calls no camera endpoint — snapshot, frame_ext, stream, stream_ext — and no
route or screen of the ERP leads to one. Only state and results come from a cabinet.
"""
import re
from pathlib import Path

from app.cabinet import contract
from app.cabinet.client import CabinetClient
from app.main import app

_REPO = Path(__file__).resolve().parents[2]
_CAMERA = re.compile(r"camera|snapshot|/stream|/frame", re.I)


def test_the_contract_has_no_camera_endpoint():
    hits = [(k, e.path) for k, e in contract.ENDPOINTS.items()
            if _CAMERA.search(k) or _CAMERA.search(e.path)]
    assert hits == []


def test_the_cabinet_client_has_no_camera_call():
    assert [n for n in dir(CabinetClient) if _CAMERA.search(n)] == []


def test_no_erp_route_leads_to_a_camera():
    paths = [getattr(r, "path", "") for r in app.routes]
    assert [p for p in paths if _CAMERA.search(p)] == []


def test_no_screen_asks_for_a_camera_picture():
    src = _REPO / "frontend" / "src"
    pat = re.compile(r"camera/(frame|stream)|snapshot|getCamera|stream_url", re.I)
    hits = [f"{f.relative_to(src)}:{i}" for f in src.rglob("*.ts*")
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1)
            if pat.search(line)]
    assert hits == []
