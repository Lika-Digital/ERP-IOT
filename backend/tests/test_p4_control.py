"""P4 (spec §6.13): Pedestal control names cabinets as the ERP records them, offers
commands only to a cabinet that can take them, and in the demo marina never sends a
command to a real cabinet — the server refuses it before any call.

The demo marina is seeded and the real collector runs once against the demo simulator.
Every request to a cabinet goes through one counting transport, so "zero calls" is
counted, not assumed.
"""
import asyncio
from datetime import timedelta

import httpx
import pytest

from app.demo import seed as demo
from app.models.cabinet import Cabinet
from app.models.metering import CommandAudit
from app.services import cabinets as svc
from simulator import demo_world as w
from simulator.demo_sim import DemoWorld, create_demo_app
from tests.conftest import TestSession

NOW = (w.EPOCH + timedelta(days=38, hours=20, minutes=30)).replace(microsecond=0)
REAL = "KRK_REAL_TEST_01"


class Counting(httpx.AsyncBaseTransport):
    def __init__(self, inner):
        self.inner, self.urls = inner, []

    async def handle_async_request(self, request):
        self.urls.append(str(request.url))
        return await self.inner.handle_async_request(request)


@pytest.fixture(scope="module")
def demo_marina(setup_test_database):
    from app.services.collector import Collector
    from app.services.pedestal_api_factory import PedestalAPIClientFactory, get_pedestal_factory
    from app.utils import time as erp_time

    db = TestSession()
    demo.remove(db)
    out = demo.seed(db, port=18080, seed_value=28, password="pw", days=1, now=NOW)
    db.close()
    world = DemoWorld(seed=28, password="pw", clock=lambda: NOW)
    transport = Counting(httpx.ASGITransport(app=create_demo_app(world)))
    erp_time._simulated_clock = lambda: NOW
    factory = get_pedestal_factory()
    factory._clients.clear()
    factory.transport = transport
    factory.sleep = lambda s: asyncio.sleep(0)
    try:
        col = Collector(factory=PedestalAPIClientFactory(), session_factory=TestSession,
                        transport=transport, sleep=lambda s: asyncio.sleep(0))
        asyncio.run(col.run_all_once())
        yield out["marina_id"], transport
    finally:
        erp_time._simulated_clock = None
        factory.transport = None
        factory.sleep = None
        factory._clients.clear()
        db = TestSession()
        real = [c.id for c in db.query(Cabinet).filter(Cabinet.display_id == REAL)]
        db.query(CommandAudit).filter(CommandAudit.cabinet_id.in_(real)).delete(
            synchronize_session=False)
        db.query(Cabinet).filter(Cabinet.id.in_(real)).delete(synchronize_session=False)
        db.commit()
        demo.remove(db)
        db.close()


def _cab(mid, display_id):
    db = TestSession()
    try:
        return db.query(Cabinet).filter(Cabinet.marina_id == mid,
                                        Cabinet.display_id == display_id).one()
    finally:
        db.close()


def _first_sim(mid):
    db = TestSession()
    try:
        return (db.query(Cabinet).filter(Cabinet.marina_id == mid)
                .order_by(Cabinet.id).first())
    finally:
        db.close()


def test_the_list_is_the_erps_cabinets_named_by_display_id(client, admin_headers, demo_marina):
    mid, _ = demo_marina
    body = client.get(f"/api/marinas/{mid}/control/cabinets", headers=admin_headers).json()
    assert body["demo"] is True
    db = TestSession()
    try:
        want = [c.display_id for c in db.query(Cabinet).filter(Cabinet.marina_id == mid)
                .order_by(Cabinet.id)]
    finally:
        db.close()
    assert [c["display_id"] for c in body["cabinets"]] == want
    assert all(c["simulated"] for c in body["cabinets"])


def test_the_live_panel_is_the_chosen_cabinet_named_by_the_erp_not_by_the_cabinet(
        client, admin_headers, demo_marina):
    mid, transport = demo_marina
    cab = _cab(mid, "SIM_C_04")
    before = len(transport.urls)
    r = client.get(f"/api/marinas/{mid}/dashboard", params={"cabinet": cab.id},
                   headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cabinet"]["display_id"] == "SIM_C_04" and body["cabinet"]["simulated"] is True
    # read through THAT cabinet's own client, not the marina's first cabinet (O65)
    asked = transport.urls[before:]
    assert asked and all("/c/SIM_C_04/" in u for u in asked), asked
    # what the simulator calls itself ("Ormar 1", "Krk") is never the ERP's name for it
    assert "Ormar 1" not in body["cabinet"]["display_id"]


def test_only_an_online_cabinet_in_smart_mode_is_controllable(client, admin_headers, demo_marina):
    mid, _ = demo_marina
    first = _first_sim(mid)
    db = TestSession()
    try:
        off = db.get(Cabinet, _cab(mid, "SIM_B_03").id)
        off.smart_mode = False
        gone = db.get(Cabinet, _cab(mid, "SIM_B_02").id)
        gone.last_heartbeat_at = NOW - timedelta(hours=1)
        db.commit()
    finally:
        db.close()
    cabs = {c["display_id"]: c for c in client.get(
        f"/api/marinas/{mid}/control/cabinets", headers=admin_headers).json()["cabinets"]}
    assert cabs[first.display_id]["controllable"] is True
    assert cabs[first.display_id]["sentence"] is None
    assert cabs["SIM_B_03"]["controllable"] is False and "Smart Mode is off" in cabs["SIM_B_03"]["sentence"]
    assert cabs["SIM_B_02"]["controllable"] is False and "offline" in cabs["SIM_B_02"]["sentence"]


def test_a_command_names_its_cabinet_and_goes_only_there(client, admin_headers, demo_marina):
    mid, transport = demo_marina
    cab = _cab(mid, "SIM_C_04")
    before = len(transport.urls)
    r = client.post(f"/api/marinas/{mid}/sessions/999999/stop", params={"cabinet": cab.id},
                    json={"reason": "test stop"}, headers=admin_headers)
    assert r.status_code in (200, 404, 409), r.text
    sent = transport.urls[before:]
    assert sent and all("/c/SIM_C_04/" in u for u in sent), sent
    # all demo cabinets share pedestal pk 1: without the ERP's id it would be ambiguous
    r = client.post(f"/api/marinas/{mid}/sessions/999999/stop",
                    params={"cabinet": cab.id, "pedestal_id": 2},
                    json={"reason": "test stop"}, headers=admin_headers)
    assert r.status_code == 422


def test_in_the_demo_marina_a_real_cabinet_gets_no_command_and_no_call(
        client, admin_headers, demo_marina):
    mid, transport = demo_marina
    db = TestSession()
    try:
        real = svc.provision_cabinet(
            db, marina_id=mid, pedestal_pk=1, display_id=REAL, device_type="full",
            base_url="http://100.64.0.9:8000", service_email="erp@krk.invalid",
            service_password="real-cabinet-pw", is_simulated=False)
        real_id = real.id
    finally:
        db.close()
    before = len(transport.urls)
    for method, path, body in (
            ("post", "/sessions/41/stop", {"reason": "should never go"}),
            ("post", "/sessions/41/allow", {"reason": "should never go"}),
            ("post", "/sessions/41/deny", {"reason": "should never go"}),
            ("post", "/pedestals/1/outlets/Q1/cmd", {"action": "stop", "reason": "should never go"}),
            ("post", "/pedestals/1/diagnostics", {"reason": "should never go"}),
            ("post", "/alarms/7/acknowledge", None)):
        r = client.request(method.upper(), f"/api/marinas/{mid}{path}",
                           params={"cabinet": real_id}, json=body, headers=admin_headers)
        assert r.status_code == 409, (path, r.text)
        assert r.json()["detail"]["code"] == "demo_marina_real_cabinet"
    assert transport.urls[before:] == []          # nothing reached any cabinet
    db = TestSession()
    try:
        rows = db.query(CommandAudit).filter(CommandAudit.cabinet_id == real_id).all()
        assert len(rows) == 5                       # every refused command is on record
        assert {r.outcome for r in rows} == {"demo_marina_real_cabinet"}
        assert all(r.completed_at is not None and r.reason == "should never go" for r in rows)
    finally:
        db.close()
    entry = next(c for c in client.get(f"/api/marinas/{mid}/control/cabinets",
                                       headers=admin_headers).json()["cabinets"]
                 if c["id"] == real_id)
    assert entry["simulated"] is False and entry["controllable"] is False
    assert "demo marina" in entry["sentence"]
