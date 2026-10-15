"""D28 — the demo marina (spec §6.11): real and simulated never mix where it costs.

The database rules (simulated <=> the simulator's address, a PK unique per cabinet
server, never billed) are schema probes (scripts/schema_probes.py), run here by
test_model_rules.py and on PostgreSQL by the boot check. This file is the code
on top of them: the cache per cabinet server, and the security agent.
"""
import asyncio
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.cabinet.client import CabinetClient
from simulator.cabinet_sim import create_app, make_state
from tests.conftest import TestSession, test_engine
from tests.test_d21 import NOW, _activate, _add, _alarms, _cmd, _run
from tests.test_d21 import clean  # noqa: F401 — the fixture, used through usefixtures

pytestmark = pytest.mark.usefixtures("clean")

SIM_URL = "http://127.0.0.1:18080/c/SIM_A_02"


def _provision(marina_id, *, pk=1, url, disp, sim=False):
    from app.services import cabinets as svc
    db = TestSession()
    try:
        c = svc.provision_cabinet(
            db, marina_id=marina_id, pedestal_pk=pk, display_id=disp, device_type="full",
            base_url=url, service_email="e@x", service_password="p", is_simulated=sim)
        db.commit()
        return c.id
    finally:
        db.close()


def _sim_flags():
    with test_engine.connect() as c:
        return [bool(r[0]) for r in c.execute(text(
            "SELECT simulated FROM security_alarms ORDER BY id"))]


# ── provisioning ─────────────────────────────────────────────────────────────

def test_a_simulated_cabinet_must_say_so_and_the_address_must_agree(marina_id):
    with pytest.raises(IntegrityError):
        _provision(marina_id, url=SIM_URL, disp="SIM_A_02", sim=False)
    with pytest.raises(IntegrityError):
        _provision(marina_id, url="http://100.64.0.9", disp="SIM_A_02", sim=True)
    assert _provision(marina_id, url=SIM_URL, disp="SIM_A_02", sim=True)


def test_two_real_cabinets_are_each_pedestal_1_on_their_own_server(marina_id):
    _provision(marina_id, url="http://100.64.0.1", disp="MAR_KRK_ORM_01")
    _provision(marina_id, url="http://100.64.0.2", disp="MARINA_IOT_01")
    with pytest.raises(IntegrityError):
        _provision(marina_id, url="http://100.64.0.2", disp="MARINA_IOT_02")


# ── the cached copy is per cabinet server ────────────────────────────────────

def test_stale_fallback_never_returns_another_servers_data(setup_test_database, marina_id):
    """Two cabinet servers in one marina answer the same path; when one goes quiet,
    its stale copy is its own, never the other's (D28)."""
    a, b = make_state("full"), make_state("retrofit")
    a.display_id, b.display_id = "MAR_KRK_ORM_01", "MARINA_IOT_01"

    def client(url, st):
        return CabinetClient(marina_id=marina_id, base_url=url, service_email=st.service_email,
                             service_password=st.service_password,
                             transport=httpx.ASGITransport(app=create_app(st)),
                             sleep=lambda s: asyncio.sleep(0))

    ca, cb = client("http://100.64.0.1", a), client("http://100.64.0.2", b)
    db = TestSession()
    try:
        assert asyncio.run(cb.health(db)).code == "ok"
        assert asyncio.run(ca.health(db)).code == "ok"      # written after b: the old bug's winner
        b.fail_next = [500] * 10
        out = asyncio.run(cb.health(db))
        assert out.code == "stale"
        assert out.data["1"]["opta_client_id"] == "MARINA_IOT_01"
    finally:
        db.close()


# ── the security agent ───────────────────────────────────────────────────────

def test_an_alarm_from_a_simulated_cabinet_is_marked_simulated(marina_id):
    real = _provision(marina_id, url="http://100.64.0.1", disp="MAR_KRK_ORM_01")
    sim = _provision(marina_id, pk=2, url=SIM_URL, disp="SIM_A_02", sim=True)
    late = NOW.replace(hour=2)
    _add(_cmd(real, late), _cmd(sim, late + timedelta(minutes=1)))
    _activate("socket_cmd_odd_hour")
    _run()
    assert sorted(_sim_flags()) == [False, True]


def test_a_demo_click_is_never_the_baseline_of_a_real_command(marina_id):
    """socket_cmd_new_ip: the account's history on SIMULATED cabinets does not count
    for a command on a REAL one — so no 'known address' and no 'new address' either."""
    real = _provision(marina_id, url="http://100.64.0.1", disp="MAR_KRK_ORM_01")
    sim = _provision(marina_id, pk=2, url=SIM_URL, disp="SIM_A_02", sim=True)
    _add(_cmd(sim, NOW - timedelta(days=5), actor="b@m", ip="10.0.0.1"),
         _cmd(real, NOW - timedelta(hours=1), actor="b@m", ip="198.51.100.4"))
    _activate("socket_cmd_new_ip")
    _run()
    assert _alarms("socket_cmd_new_ip") == []


def test_a_snapshot_is_matched_to_its_cabinet_by_server_as_well_as_pk(marina_id):
    """door_no_window reads status_ext snapshots from the cache. With two servers in one
    marina, 'pedestal 1' is two cabinets: the server in the key decides, and a key
    that cannot decide raises nothing rather than blame the wrong cabinet."""
    _provision(marina_id, url="http://100.64.0.1", disp="MAR_KRK_ORM_01")
    _provision(marina_id, url="http://100.64.0.2", disp="MARINA_IOT_01")
    from app.models.cache import PedestalCache
    path = "pedestals.status_ext:/api/ext/pedestals/1/status"
    _add(PedestalCache(marina_id=marina_id, cache_key=f"{path}@http://100.64.0.2",
                       last_seen_data={"door_state": "open"}, last_synced_at=NOW - timedelta(hours=1)),
         PedestalCache(marina_id=marina_id, cache_key=path,          # before 6.0: no server
                       last_seen_data={"door_state": "open"}, last_synced_at=NOW - timedelta(hours=2)))
    _activate("door_no_window")
    _run()
    got = _alarms("door_no_window")
    assert [a["title"] for a in got] == ["MARINA_IOT_01: door open outside a service window"]


# ── the collector: cabinet servers in parallel, each on its own ──────────────

class _Router(httpx.AsyncBaseTransport):
    """Two cabinet servers by host. 'slow' answers only once 'fast' has been asked —
    so it can only succeed if the two are polled AT THE SAME TIME."""

    def __init__(self):
        self.fast_seen = asyncio.Event()
        self.apps = {h: httpx.ASGITransport(app=create_app(make_state("full")))
                     for h in ("slow", "fast")}

    async def handle_async_request(self, request):
        if request.url.host == "slow":
            await asyncio.wait_for(self.fast_seen.wait(), timeout=2)
        else:
            self.fast_seen.set()
        return await self.apps[request.url.host].handle_async_request(request)


def _two_servers(marina_id):
    st = make_state("full")
    from app.services import cabinets as svc
    db = TestSession()
    try:
        for host in ("slow", "fast"):           # 'slow' first: sequential order meets it first
            svc.provision_cabinet(
                db, marina_id=marina_id, pedestal_pk=1, display_id=f"MAR_{host.upper()}_01",
                device_type="full", base_url=f"http://{host}", service_email=st.service_email,
                service_password=st.service_password)
        db.commit()
    finally:
        db.close()


def _polled():
    with test_engine.connect() as c:
        return {r[0]: r[1] is not None for r in c.execute(text(
            "SELECT display_id, last_polled_at FROM cabinets ORDER BY id"))}


def _collector(parallel):
    from app.services.collector import Collector
    from app.services.pedestal_api_factory import PedestalAPIClientFactory

    async def no_wait(_s):
        return None
    return Collector(factory=PedestalAPIClientFactory(), session_factory=TestSession,
                     transport=_Router(), sleep=no_wait, parallel=parallel)


def test_cabinet_servers_are_polled_at_the_same_time(marina_id):
    _two_servers(marina_id)
    asyncio.run(_collector(parallel=2).tick())
    assert _polled() == {"MAR_SLOW_01": True, "MAR_FAST_01": True}


def test_one_failing_server_does_not_stop_the_others(marina_id, caplog):
    """One at a time, 'slow' waits for 'fast' that never comes and fails (as a dead
    cabinet would); 'fast' is still collected in the same tick."""
    _two_servers(marina_id)
    col = _collector(parallel=1)
    asyncio.run(col.tick())
    assert _polled() == {"MAR_SLOW_01": False, "MAR_FAST_01": True}
    assert "server http://slow failed" in caplog.text
