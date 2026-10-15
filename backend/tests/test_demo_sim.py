"""D28 — the demo marina's simulated cabinets, through the ERP's own client (spec §6.11)."""
import asyncio
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.cabinet.client import CabinetClient
from simulator import demo_world as w
from simulator.demo_sim import SERVICE_EMAIL, DemoWorld, create_demo_app

T0 = w.EPOCH + timedelta(days=40, hours=9)


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def _setup(clock=None):
    clock = clock or Clock(T0)
    world = DemoWorld(seed=28, password="pw", clock=clock)
    transport = httpx.ASGITransport(app=create_demo_app(world))

    def client(cid):
        return CabinetClient(marina_id=1, base_url=f"http://127.0.0.1:18080/c/{cid}",
                             service_email=SERVICE_EMAIL, service_password="pw",
                             transport=transport)
    return world, clock, transport, client


def run(c):
    return asyncio.run(c)


def test_each_simulated_cabinet_is_its_own_server_with_its_own_berths():
    world, _clock, _t, client = _setup()
    c = client("SIM_C_04")
    health = run(c.health())
    assert health.code == "ok" and health.data["1"]["opta_client_id"] == "SIM_C_04"
    berths = run(c.list_berths())
    assert [b["name"] for b in berths.data] == ["C-07", "C-08"]
    for b in berths.data:
        want = 0
        if w.occupied(28, b["name"], T0):
            want = 2 if w.wrong_vessel(28, b["name"], T0) else 1
        assert b["state_code"] == want
    assert len(world.states) == 74


def test_the_meter_a_cabinet_reports_is_the_worlds_and_only_rises():
    _world, clock, _t, client = _setup()
    c = client("SIM_A_02")                       # berths A-03, A-04 — 20 m, Q1 and Q2
    seen = []
    for h in range(0, 48, 3):
        clock.t = T0 + timedelta(hours=h)
        load = run(c.pedestal_load(1))
        q1 = next(s for s in load.data["sockets"] if s["socket_id"] == 1)
        b = next(b for b in w.berths() if b.number == "A-03")
        assert q1["energy_kwh"] == w.register_kwh(28, b, clock.t)
        seen.append(q1["energy_kwh"])
    assert seen == sorted(seen)


def test_offline_freezes_the_cabinet_past_the_erps_threshold_and_reset_restores_it():
    world, clock, _t, client = _setup()
    assert world.scenario("offline", "SIM_D_03")["ok"]
    clock.t = T0 + timedelta(minutes=1)
    hb = run(client("SIM_D_03").health()).data["1"]["last_heartbeat"]
    # the heartbeat is stamped by the phase-2 simulator against the wall clock
    def age(stamp):
        return datetime.now(timezone.utc).replace(tzinfo=None) - datetime.fromisoformat(stamp.rstrip("Z"))
    assert age(hb) > timedelta(minutes=10)
    assert world.scenario("reset", None)["ok"]
    hb = run(client("SIM_D_03").health()).data["1"]["last_heartbeat"]
    assert age(hb) < timedelta(seconds=30)


def test_wrong_vessel_on_command():
    world, _clock, _t, client = _setup()
    assert world.scenario("wrong-vessel", "C-11")["ok"]
    rows = run(client("SIM_C_06").list_berths()).data
    c11 = next(b for b in rows if b["name"] == "C-11")
    assert c11["state_code"] == 2 or not w.occupied(28, "C-11", T0)


def test_a_scenario_never_names_a_real_cabinet_or_berth():
    world, *_ = _setup()
    before = world.public()
    for name, target in (("offline", "MAR_KRK_ORM_01"), ("offline", "MARINA_IOT_01"),
                         ("wrong-vessel", "A-01"), ("wrong-vessel", "B-02"),
                         ("offline", None), ("nonsense", "SIM_C_04")):
        assert world.scenario(name, target)["ok"] is False
    assert world.public() == before


def test_the_scenario_route_answers_and_the_phase2_test_routes_are_closed():
    async def go():
        world, _clock, transport, _client = _setup()
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as h:
            ok = await h.post("/__demo/scenario", json={"name": "offline", "target": "SIM_E_01"})
            bad = await h.post("/__demo/scenario", json={"name": "offline", "target": "MAR_KRK_ORM_01"})
            closed = await h.patch("/c/SIM_E_01/__sim/credentials",
                                   json={"email": "x", "password": "y"})
            return ok.status_code, bad.status_code, closed.status_code, world.states["SIM_E_01"]
    ok, bad, closed, st = run(go())
    assert (ok, bad, closed) == (200, 400, 404)
    assert st.service_password == "pw"


def test_a_long_running_server_does_not_grow():
    world, _clock, _t, client = _setup()
    c = client("SIM_QN_13")                      # the last pair: one berth only
    for _ in range(150):
        run(c.health())
    assert len(world.states["SIM_QN_13"].calls) <= 101
    assert [b["name"] for b in run(c.list_berths()).data] == ["QN-25"]


def test_the_simulator_holds_no_way_to_reach_anything():
    """It only answers. No HTTP library in the server code; the one urllib call is
    the command line talking to this server on 127.0.0.1."""
    sim = Path(__file__).resolve().parents[1] / "simulator"
    for f in ("demo_world.py", "demo_sim.py", "cabinet_sim.py"):
        text = (sim / f).read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import|from)\s+(httpx|requests|aiohttp|socket)\b", text, re.M), f
    demo = (sim / "demo_sim.py").read_text(encoding="utf-8")
    assert demo.count("urlopen(") == 1 and 'f"http://127.0.0.1:{port}{path}"' in demo


def test_the_vps_unit_reaches_only_loopback_and_is_off_with_one_command():
    unit = (Path(__file__).resolve().parents[2] / "deploy" / "erp-sim.service").read_text(
        encoding="utf-8")
    for line in ("User=erp-sim", "IPAddressDeny=any", "IPAddressAllow=localhost",
                 "NoNewPrivileges=yes", "ProtectSystem=strict"):
        assert f"\n{line}\n" in unit, line
    assert "sudo systemctl disable --now erp-sim" in unit
    assert "-m simulator.demo_sim serve" in unit
