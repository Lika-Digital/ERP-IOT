"""D27 phase 1 + D30 — a berth's detail and its vessel (spec §6.10, §6.12, §10.12).

The demo marina is seeded and the real collector runs once against the demo
simulator; the detail is then read through the API. The owner is personal data
(D15): never on the map or the dashboard, only on request, and every read audited.
"""
import asyncio
import json
from datetime import timedelta

import httpx
import pytest

from app.demo import seed as demo
from app.models.berth import Berth, BerthVessel, Vessel
from app.models.cache import AuditLog
from app.models.user import User, UserMarinaAccess
from simulator import demo_world as w
from simulator.demo_sim import DemoWorld, create_demo_app
from tests.conftest import TestSession

NOW = (w.EPOCH + timedelta(days=38, hours=20, minutes=30)).replace(microsecond=0)


@pytest.fixture(scope="module")
def demo_marina(setup_test_database):
    from app.services.collector import Collector
    from app.services.pedestal_api_factory import PedestalAPIClientFactory
    from app.utils import time as erp_time

    db = TestSession()
    demo.remove(db)
    out = demo.seed(db, port=18080, seed_value=28, password="pw", days=1, now=NOW)
    manager = db.query(User).filter(User.email == "manager@test.erp").one()
    db.add(UserMarinaAccess(user_id=manager.id, marina_id=out["marina_id"]))
    db.commit()
    db.close()
    erp_time._simulated_clock = lambda: NOW
    try:
        world = DemoWorld(seed=28, password="pw", clock=lambda: NOW)
        col = Collector(factory=PedestalAPIClientFactory(), session_factory=TestSession,
                        transport=httpx.ASGITransport(app=create_demo_app(world)),
                        sleep=lambda s: asyncio.sleep(0))
        asyncio.run(col.run_all_once())
    finally:
        erp_time._simulated_clock = None
    yield out["marina_id"]
    db = TestSession()
    db.query(UserMarinaAccess).filter(UserMarinaAccess.marina_id == out["marina_id"]).delete()
    db.commit()
    demo.remove(db)
    db.close()


def _berth_id(mid, number):
    db = TestSession()
    try:
        return db.query(Berth.id).filter(Berth.marina_id == mid, Berth.berth_number == number).scalar()
    finally:
        db.close()


def _detail(client, headers, mid, number, now=NOW):
    from app.utils import time as erp_time
    erp_time._simulated_clock = lambda: now
    try:
        return client.get(f"/api/marinas/{mid}/berths/{_berth_id(mid, number)}/detail", headers=headers)
    finally:
        erp_time._simulated_clock = None


def test_the_detail_carries_the_vessel_but_never_the_owner(client, admin_headers, demo_marina):
    r = _detail(client, admin_headers, demo_marina, "A-05")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["vessel"]["name"] and body["vessel"]["registration"].startswith("DM-")
    assert body["vessel"]["has_owner"] is True
    text = json.dumps(body)
    assert "owner_name" not in text and "Demo owner" not in text and "demo.invalid" not in text


def test_the_cabinets_own_result_is_shown_from_what_the_collector_stored(client, admin_headers,
                                                                          demo_marina):
    for number in ("A-05", "A-06", "C-11", "QN-03"):
        a = _detail(client, admin_headers, demo_marina, number).json()["analysis"]
        occupied = w.occupied(28, number, NOW)
        assert a["occupied"] is occupied, number
        want = None if not occupied else ("no_match" if w.wrong_vessel(28, number, NOW) else "match")
        assert a["match"] == want, number
        assert a["is_stale"] is False


def test_the_four_assessment_functions_say_not_available_and_offer_no_control(
        client, admin_headers, demo_marina):
    fs = _detail(client, admin_headers, demo_marina, "A-05").json()["functions"]
    assert [f["key"] for f in fs] == ["reference_upload", "occupancy_run", "match_run", "sector", "guard"]
    assert all(f["available"] is False for f in fs)
    assert {f["sentence"] for f in fs[1:]} == {"Not available on this cabinet"}
    assert [f["requires"] for f in fs[1:]] == ["R27", "R28", "R29", "R30"]


def test_a_real_berth_not_connected_yet_has_no_cabinet_vessel_or_result(client, admin_headers,
                                                                        demo_marina):
    body = _detail(client, admin_headers, demo_marina, "A-01").json()
    assert body["cabinet"] is None and body["vessel"] is None and body["analysis"] is None
    assert (body["berth"]["status_code"], body["berth"]["berth_colour"]) == ("no_cabinet", "none")


def test_neither_vessel_nor_owner_reaches_the_map_or_dashboard(client, admin_headers, demo_marina):
    r = client.get(f"/api/marinas/{demo_marina}/overview", headers=admin_headers)
    text = r.text
    assert r.status_code == 200
    for needle in ("Demo owner", "demo.invalid", "DM-10", "Aurora", "owner"):
        assert needle not in text, needle


def test_reading_the_owner_is_audited_without_the_owners_data(client, manager_headers, demo_marina):
    bid = _berth_id(demo_marina, "A-05")
    r = client.get(f"/api/marinas/{demo_marina}/berths/{bid}/vessel/owner", headers=manager_headers)
    assert r.status_code == 200 and r.json()["owner_name"].startswith("Demo owner")
    db = TestSession()
    try:
        row = (db.query(AuditLog).filter(AuditLog.marina_id == demo_marina,
                                         AuditLog.action == "read_vessel_owner")
               .order_by(AuditLog.id.desc()).first())
        assert row is not None and row.details == {"berth": "A-05"}
    finally:
        db.close()


def test_only_an_admin_with_a_reason_edits_the_vessel(client, admin_headers, manager_headers,
                                                     demo_marina):
    bid = _berth_id(demo_marina, "B-07")
    url = f"/api/marinas/{demo_marina}/berths/{bid}/vessel"
    body = {"name": "Nova", "registration": "ST-1", "owner_name": "Demo X",
            "owner_contact": "x@demo.invalid", "reason": "new season contract"}
    assert client.put(url, json=body, headers=manager_headers).status_code == 403
    assert client.put(url, json={**body, "reason": "ok"}, headers=admin_headers).status_code == 422
    assert client.put(url, json={**body, "name": "   "}, headers=admin_headers).status_code == 422
    r = client.put(url, json=body, headers=admin_headers)
    assert r.status_code == 200, r.text
    detail = _detail(client, admin_headers, demo_marina, "B-07").json()
    assert detail["vessel"]["name"] == "Nova" and detail["vessel"]["registration"] == "ST-1"
    db = TestSession()
    try:
        row = (db.query(AuditLog).filter(AuditLog.action == "set_vessel")
               .order_by(AuditLog.id.desc()).first())
        assert row.details == {"berth": "B-07", "reason": "new season contract", "owner_changed": True}
        assert "Demo X" not in json.dumps(row.details)
    finally:
        db.close()


def test_clearing_the_vessel_keeps_its_history(client, admin_headers, demo_marina):
    bid = _berth_id(demo_marina, "B-08")
    url = f"/api/marinas/{demo_marina}/berths/{bid}/vessel"
    r = client.request("DELETE", url, json={"reason": "left the marina"}, headers=admin_headers)
    assert r.status_code == 200
    assert _detail(client, admin_headers, demo_marina, "B-08").json()["vessel"] is None
    db = TestSession()
    try:
        rows = db.query(BerthVessel).filter(BerthVessel.berth_id == bid).all()
        assert len(rows) == 1 and rows[0].valid_to is not None
        assert db.get(Vessel, rows[0].vessel_id) is not None
    finally:
        db.close()


def test_a_berth_of_another_marina_is_404(client, admin_headers, demo_marina, marina_id):
    bid = _berth_id(demo_marina, "A-05")
    r = client.get(f"/api/marinas/{marina_id}/berths/{bid}/detail", headers=admin_headers)
    assert r.status_code == 404


def test_editing_the_name_without_the_owner_keeps_the_owner(client, admin_headers, demo_marina):
    bid = _berth_id(demo_marina, "C-03")
    url = f"/api/marinas/{demo_marina}/berths/{bid}/vessel"
    r = client.put(url, json={"name": "Renamed", "registration": None, "reason": "typo fixed"},
                   headers=admin_headers)
    assert r.status_code == 200
    owner = client.get(f"{url}/owner", headers=admin_headers).json()
    assert owner["owner_name"].startswith("Demo owner")
    db = TestSession()
    try:
        row = (db.query(AuditLog).filter(AuditLog.action == "set_vessel")
               .order_by(AuditLog.id.desc()).first())
        assert row.details["owner_changed"] is False
    finally:
        db.close()
