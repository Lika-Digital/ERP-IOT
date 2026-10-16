"""D23 — the main dashboard (spec §6.6): the map and the three cards, from the database.

The demo marina (D28) is seeded, the REAL collector runs one round against the demo
simulator, and the dashboard is then built with no cabinet call at all (O64). The
expected colours are worked out from the simulator's world independently, not from
the code under test.
"""
import asyncio
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest

from app.cabinet import marina_state
from app.demo import seed as demo
from app.models.berth import Berth, BerthReservation
from app.models.cabinet import Cabinet, Outlet
from app.models.marina import Marina
from app.models.metering import ConsumptionInterval
from app.models.security import SecurityAgentPass, SecurityAlarm
from app.services import overview
from simulator import demo_world as w
from simulator.demo_sim import DemoWorld, create_demo_app
from tests.conftest import TestSession

# an hour in which seed 28 has two cabinet alarms (SIM_A_10, SIM_E_08)
NOW = (w.EPOCH + timedelta(days=38, hours=20, minutes=30)).replace(microsecond=0)
LATER = NOW + timedelta(minutes=3)
REAL = {"A-01", "A-02", "B-01", "B-02"}


def _collect(at, world=None):
    from app.services.collector import Collector
    from app.services.pedestal_api_factory import PedestalAPIClientFactory
    from app.utils import time as erp_time

    erp_time._simulated_clock = lambda: at
    try:
        world = world or DemoWorld(seed=28, password="pw", clock=lambda: at)
        col = Collector(factory=PedestalAPIClientFactory(), session_factory=TestSession,
                        transport=httpx.ASGITransport(app=create_demo_app(world)),
                        sleep=lambda s: asyncio.sleep(0))
        asyncio.run(col.run_all_once())
    finally:
        erp_time._simulated_clock = None


@pytest.fixture(scope="module")
def seeded(setup_test_database):
    db = TestSession()
    demo.remove(db)
    out = demo.seed(db, port=18080, seed_value=28, password="pw", days=8, now=NOW)
    db.close()
    _collect(LATER)
    yield out
    db = TestSession()
    demo.remove(db)
    db.close()


@pytest.fixture
def db(seeded):
    s = TestSession()
    yield s
    s.close()


def _marina(db, seeded) -> Marina:
    return db.get(Marina, seeded["marina_id"])


def _expected_colour(db, mid: int, number: str) -> str:
    if number in REAL:
        return "grey"
    if w.occupied(28, number, LATER):
        return "red" if w.wrong_vessel(28, number, LATER) else "blue"
    b = next(b for b in w.berths() if b.number == number)
    if w.power_kw(28, b, LATER) > 0:
        return "orange"
    reserved = (db.query(BerthReservation.id).join(Berth, Berth.id == BerthReservation.berth_id)
                .filter(Berth.marina_id == mid, Berth.berth_number == number,
                        BerthReservation.starts_at <= LATER, BerthReservation.ends_at > LATER)
                .first())
    return "yellow" if reserved else "green"


def test_every_berth_of_the_marina_is_on_the_map_with_the_worlds_colour(seeded, db):
    """O64: all 150 — not the 2 of the first cabinet; colour = occupancy only (v17)."""
    mid = seeded["marina_id"]
    state = marina_state.build(db, mid, LATER)
    assert len(state["berths"]) == 150
    got = {b["number"]: b["berth_colour"] for b in state["berths"]}
    want = {b.number: _expected_colour(db, mid, b.number) for b in w.berths()}
    assert got == want
    assert set(got.values()) >= {"blue", "green", "grey"}
    for b in state["berths"]:
        assert b["svg_id"] == f"berth-{b['number']}"
        assert b["simulated"] is (b["number"] not in REAL)
        if b["number"] in REAL:
            assert b["status_code"] == "no_cabinet" and b["alarm"] == []


def test_a_cabinet_alarm_is_a_marker_on_both_its_berths_never_the_colour(seeded, db):
    mid = seeded["marina_id"]
    state = {b["number"]: b for b in marina_state.build(db, mid, LATER)["berths"]}
    raised = {spec.display_id: w.cabinet_alarm(28, spec, LATER) for spec in w.cabinets()}
    want_code = {"moisture": "water_leak", "temperature": "too_hot"}
    seen = 0
    for spec in w.cabinets():
        for b in spec.berths:
            row = state[b.number]
            kind = raised[spec.display_id]
            assert [a["code"] for a in row["alarm"]] == ([want_code[kind]] if kind else [])
            assert row["berth_colour"] == _expected_colour(db, mid, b.number)
            seen += bool(kind)
    assert seen, "seed 28 at this hour has no cabinet alarm — pick another hour"


def test_no_cabinet_is_called_to_draw_the_dashboard(seeded, db, monkeypatch):
    from app.cabinet.client import CabinetClient

    async def refuse(*a, **k):
        raise AssertionError("the dashboard called a cabinet")
    monkeypatch.setattr(CabinetClient, "call", refuse)
    out = overview.build(db, _marina(db, seeded), LATER)
    assert len(out["berths"]) == 150 and out["map_svg"] == "demo-marina.svg"


def test_occupancy_card_counts_vessels_over_known_berths(seeded, db):
    out = overview.build(db, _marina(db, seeded), LATER)
    card = next(c for c in out["cards"] if c["key"] == "occupancy")
    berths = out["berths"]
    occupied = sum(w.occupied(28, b.number, LATER) for b in w.berths() if b.number not in REAL)
    assert card["occupied"] == occupied and card["known"] == 146 and card["unknown"] == 4
    assert card["percent"] == round(occupied * 100 / 146)
    assert card["reserved"] == sum(1 for b in berths if b["signals"]["reservation"] == "YES")
    assert card["state"] == "fresh" and card["simulated"] == "all"


def test_a_silent_cabinet_makes_the_occupancy_card_partial_and_its_berths_grey(seeded, db):
    mid = seeded["marina_id"]
    later = LATER + timedelta(minutes=11)      # every cache row now older than 10 min ...
    cab = db.query(Cabinet).filter(Cabinet.marina_id == mid,
                                   Cabinet.display_id == "SIM_A_02").one()
    keep = cab.last_heartbeat_at
    try:
        state = marina_state.build(db, mid, later)
        assert all(b["berth_colour"] == "grey" for b in state["berths"])
        card = overview.occupancy_card(_marina(db, seeded), state["berths"], None, later)
        assert card["state"] == "stale" and card["percent"] is None
    finally:
        cab.last_heartbeat_at = keep
        db.commit()
    # ... and one cabinet silent among fresh ones: partial, the number still shown
    state = marina_state.build(db, mid, LATER)
    rows = [dict(b) for b in state["berths"]]
    for b in rows:
        if b["cabinet"] == "SIM_A_02":
            b.update(berth_colour="grey", status_code="no_contact")
    card = overview.occupancy_card(_marina(db, seeded), rows, LATER, LATER)
    assert card["state"] == "partial" and card["silent"] == 2 and card["percent"] is not None


def test_energy_today_is_since_local_midnight_and_compares_the_same_part_of_the_day(seeded, db):
    m = _marina(db, seeded)
    out = overview.energy_card(db, m, LATER)
    from zoneinfo import ZoneInfo
    start = overview.local_midnight_utc(LATER, ZoneInfo("Europe/Zagreb"))
    assert start.hour in (22, 23)                # 00:00 Zagreb is 22:00 or 23:00 UTC
    ids = [o.id for o in db.query(Outlet).join(Cabinet).filter(
        Cabinet.marina_id == m.id, Outlet.medium == "electricity")]
    today = overview.energy_between(db, ids, start, LATER)
    assert out["electricity_kwh"] == float(round(today, 1)) and today > 0
    yday = overview.energy_between(db, ids, start - timedelta(days=1), LATER - timedelta(days=1))
    assert out["delta_yesterday_pct"] == round(float((today - yday) / yday * 100), 1)
    assert out["water_m3"] is None               # O62: "—", never 0
    assert out["state"] == "fresh" and out["simulated"] == "all"


def test_a_straddling_interval_counts_pro_rata(seeded, db):
    m = _marina(db, seeded)
    outlet = db.query(Outlet).join(Cabinet).filter(Cabinet.marina_id == m.id).first()
    t0 = NOW - timedelta(days=30)
    db.add(ConsumptionInterval(outlet_id=outlet.id, from_at=t0, to_at=t0 + timedelta(hours=2),
                               energy_kwh=Decimal("4"), meter_from=Decimal("1"),
                               meter_to=Decimal("5"), source="register"))
    db.commit()
    try:
        got = overview.energy_between(db, [outlet.id], t0 + timedelta(hours=1), t0 + timedelta(days=1))
        assert got == Decimal("2")
    finally:
        db.query(ConsumptionInterval).filter(ConsumptionInterval.outlet_id == outlet.id,
                                             ConsumptionInterval.from_at == t0).delete()
        db.commit()


def test_security_card_is_stale_when_the_agent_does_not_run(seeded, db):
    m = _marina(db, seeded)
    db.query(SecurityAgentPass).delete()
    db.commit()
    card = overview.security_card(db, m, [], LATER)
    assert card["state"] == "stale" and "not run" in card["sentence"]
    db.add(SecurityAgentPass(finished_at=LATER - timedelta(minutes=2), rules=7, opened=0))
    db.commit()
    try:
        card = overview.security_card(db, m, [], LATER)
        assert (card["state"], card["open"], card["sentence"]) == ("fresh", 0, "No open alerts")
        card = overview.security_card(db, m, [], LATER + timedelta(minutes=11))
        assert card["state"] == "stale" and "silent since" in card["sentence"]
    finally:
        db.query(SecurityAgentPass).delete()
        db.commit()


def test_simulated_alarms_are_counted_apart_never_as_real(seeded, db):
    m = _marina(db, seeded)
    db.add(SecurityAgentPass(finished_at=LATER, rules=7, opened=2))
    for i, (sev, sim) in enumerate((("warning", False), ("critical", True))):
        db.add(SecurityAlarm(rule_id="t", fingerprint=f"d23-{i}".ljust(64, "x"), severity=sev,
                             title="t", why="w", evidence=[], created_at=LATER, simulated=sim))
    db.commit()
    try:
        berths = marina_state.build(db, m.id, LATER)["berths"]
        on_berths = sum(len(b["alarm"]) for b in berths)        # all simulated in the demo
        card = overview.security_card(db, m, berths, LATER)
        assert card["open"] == 1 and card["worst"] == "warning"
        assert card["open_simulated"] == 1 + on_berths
    finally:
        db.query(SecurityAlarm).filter(SecurityAlarm.rule_id == "t").delete()
        db.query(SecurityAgentPass).delete()
        db.commit()


def test_the_overview_route_answers_for_the_marina_and_refuses_strangers(seeded, client,
                                                                         admin_headers):
    mid = seeded["marina_id"]
    r = client.get(f"/api/marinas/{mid}/overview", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert [c["key"] for c in body["cards"]] == ["energy", "security", "occupancy"]
    assert {c["state"] for c in body["cards"]} <= {"fresh", "partial", "stale"}
    assert len(body["cabinets"]) == 74
    assert client.get(f"/api/marinas/{mid}/overview").status_code == 401
    assert client.get("/api/marinas/999999/overview", headers=admin_headers).status_code == 404


def test_map_file_must_be_a_file_name(seeded, db):
    from sqlalchemy.exc import IntegrityError
    m = _marina(db, seeded)
    for bad in ("../etc/passwd.svg", "maps/x.svg", "x.png", ".hidden.svg", "a\\b.svg"):
        m.map_svg = bad
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
