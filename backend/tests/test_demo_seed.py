"""D28 — the demo marina in the ERP (spec §6.11): seed, history, the collector after it."""
import asyncio
from datetime import timedelta

import httpx
import pytest

from app.demo import seed as demo
from app.models.berth import Berth, BerthOutlet, BerthReservation
from app.models.cabinet import Cabinet, Outlet
from app.models.metering import ConsumptionInterval, OutletMeterState
from simulator import demo_world as w
from simulator.demo_sim import DemoWorld, create_demo_app
from tests.conftest import TestSession

NOW = (w.EPOCH + timedelta(days=40, hours=9, minutes=30)).replace(microsecond=0)
DAYS = 2


@pytest.fixture(scope="module")
def seeded(setup_test_database):
    db = TestSession()
    demo.remove(db)
    out = demo.seed(db, port=18080, seed_value=28, password="pw", days=DAYS, now=NOW)
    db.close()
    yield out
    db = TestSession()
    demo.remove(db)
    db.close()


@pytest.fixture
def db(seeded):
    s = TestSession()
    yield s
    s.close()


def test_150_berths_74_simulated_cabinets_and_the_real_pairs_unlinked(seeded, db):
    mid = seeded["marina_id"]
    berths = {b.berth_number: b for b in db.query(Berth).filter(Berth.marina_id == mid)}
    assert len(berths) == 150
    assert all(b.svg_id == f"berth-{n}" for n, b in berths.items())
    cabs = db.query(Cabinet).filter(Cabinet.marina_id == mid).all()
    assert len(cabs) == 74 and all(c.is_simulated for c in cabs)
    assert all(c.base_url == f"http://127.0.0.1:18080/c/{c.display_id}" for c in cabs)
    for n in ("A-01", "A-02", "B-01", "B-02"):                  # real: until 5d, no cabinet
        assert berths[n].cabinet_id is None
    linked = [b for b in berths.values() if b.cabinet_id is not None]
    assert len(linked) == 146
    assert float(berths["A-05"].length_m) == 20.0 and berths["QN-01"].length_m is None


def test_every_linked_berth_has_its_socket_and_a_full_cabinets_berth_its_valve(seeded, db):
    mid = seeded["marina_id"]
    for b in db.query(Berth).filter(Berth.marina_id == mid, Berth.cabinet_id.isnot(None)):
        media = sorted(o.medium for o in db.query(BerthOutlet).filter(BerthOutlet.berth_id == b.id))
        want = ["electricity"] if b.berth_number.startswith("QS-") else ["electricity", "water"]
        assert media == want, b.berth_number


def test_reservations_only_on_berths_that_are_empty_that_day(seeded, db):
    mid = seeded["marina_id"]
    rows = (db.query(BerthReservation, Berth.berth_number)
            .join(Berth, Berth.id == BerthReservation.berth_id).filter(Berth.marina_id == mid).all())
    assert len(rows) == seeded["reservations"] > 0
    for r, number in rows:
        d = w.day_of(r.starts_at)
        assert number not in w.occupied_set(28, d)
        assert r.ends_at - r.starts_at == timedelta(days=1) and r.created_by == "demo-seed"


def test_history_is_one_unbroken_series_ending_where_the_meter_state_stands(seeded, db):
    mid = seeded["marina_id"]
    cab = db.query(Cabinet).filter(Cabinet.marina_id == mid, Cabinet.display_id == "SIM_A_02").one()
    q1 = db.query(Outlet).filter(Outlet.cabinet_id == cab.id, Outlet.outlet_name == "Q1").one()
    ivs = (db.query(ConsumptionInterval).filter(ConsumptionInterval.outlet_id == q1.id)
           .order_by(ConsumptionInterval.from_at).all())
    assert ivs[0].from_at == (NOW - timedelta(days=DAYS)).replace(minute=0, second=0)
    for a, b in zip(ivs, ivs[1:]):
        assert a.to_at == b.from_at and a.meter_to == b.meter_from        # no gap, no overlap
        assert not (a.energy_kwh == 0 and b.energy_kwh == 0)             # idle hours: one row
    st = db.get(OutletMeterState, q1.id)
    assert st.read_at == NOW == ivs[-1].to_at
    a03 = next(b for b in w.berths() if b.number == "A-03")
    assert float(st.energy_kwh) == pytest.approx(w.register_kwh(28, a03, NOW), abs=1e-4)


def test_the_collector_carries_on_from_the_seed_without_a_gap(seeded, db, monkeypatch):
    from app.services.collector import Collector
    from app.services.pedestal_api_factory import PedestalAPIClientFactory
    from app.utils import time as erp_time

    later = NOW + timedelta(minutes=20)
    erp_time._simulated_clock = lambda: later
    try:
        world = DemoWorld(seed=28, password="pw", clock=lambda: later)
        col = Collector(factory=PedestalAPIClientFactory(), session_factory=TestSession,
                        transport=httpx.ASGITransport(app=create_demo_app(world)),
                        sleep=lambda s: asyncio.sleep(0))
        asyncio.run(col.tick())
    finally:
        erp_time._simulated_clock = None
    mid = seeded["marina_id"]
    cab = db.query(Cabinet).filter(Cabinet.marina_id == mid, Cabinet.display_id == "SIM_A_02").one()
    assert cab.last_polled_at is not None and cab.smart_mode is True
    q1 = db.query(Outlet).filter(Outlet.cabinet_id == cab.id, Outlet.outlet_name == "Q1").one()
    last = (db.query(ConsumptionInterval).filter(ConsumptionInterval.outlet_id == q1.id)
            .order_by(ConsumptionInterval.to_at.desc()).first())
    assert last.to_at == later and last.energy_kwh >= 0
    st = db.get(OutletMeterState, q1.id)
    a03 = next(b for b in w.berths() if b.number == "A-03")
    assert float(st.energy_kwh) == pytest.approx(w.register_kwh(28, a03, later), abs=1e-4)


def test_seeding_twice_is_refused(seeded, db):
    with pytest.raises(demo.DemoExists):
        demo.seed(db, now=NOW, days=1)


def test_simulated_history_is_deleted_after_30_days_and_never_rolled_up(seeded, db):
    from app.models.metering import ConsumptionMonthly
    from app.services import retention
    mid = seeded["marina_id"]
    outs = [o.id for o in db.query(Outlet.id).join(Cabinet, Cabinet.id == Outlet.cabinet_id)
            .filter(Cabinet.marina_id == mid)]
    before = db.query(ConsumptionInterval).filter(ConsumptionInterval.outlet_id.in_(outs)).count()
    assert before > 0
    retention.run(db, now=NOW + timedelta(days=31 + DAYS))
    assert db.query(ConsumptionInterval).filter(ConsumptionInterval.outlet_id.in_(outs)).count() == 0
    assert db.query(ConsumptionMonthly).filter(ConsumptionMonthly.outlet_id.in_(outs)).count() == 0
