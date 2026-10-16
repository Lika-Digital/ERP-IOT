"""D28 — the demo marina's world (spec §6.11): layout, and values that are functions."""
import re
from collections import Counter
from datetime import timedelta

from simulator import demo_world as w

SEED = 28
T0 = w.EPOCH + timedelta(days=40, hours=9, minutes=17)


# ── layout ───────────────────────────────────────────────────────────────────

def test_150_berths_with_stable_ids_in_the_agreed_scheme():
    bs = w.berths()
    numbers = [b.number for b in bs]
    assert len(numbers) == len(set(numbers)) == 150
    assert all(re.match(w.BERTH_RE, n) for n in numbers)
    assert Counter(b.zone for b in bs) == {"A": 20, "B": 20, "C": 20, "D": 20, "E": 20,
                                           "QN": 25, "QS": 10, "QE": 15}
    # pontoon E and the east quay never collide
    assert not {n for n in numbers if n.startswith("E-")} & {n for n in numbers if n.startswith("QE-")}
    assert all(b.svg_id == f"berth-{b.number}" for b in bs)
    assert {b.length_m for b in bs if b.zone == "A"} == {20.0}
    assert {b.length_m for b in bs if b.zone in "BC"} == {15.0}
    assert {b.length_m for b in bs if b.zone in "DE"} == {10.0}


def test_two_real_cabinets_and_74_simulated_cover_every_berth_once():
    sim = w.cabinets()
    every = w.cabinets(include_real=True)
    assert len(sim) == 74 and len(every) == 76 and all(c.simulated for c in sim)
    real = {c.display_id: [b.number for b in c.berths] for c in every if not c.simulated}
    assert real == {"MAR_KRK_ORM_01": ["A-01", "A-02"], "MARINA_IOT_01": ["B-01", "B-02"]}
    covered = Counter(b.number for c in every for b in c.berths)
    assert set(covered) == {b.number for b in w.berths()} and set(covered.values()) == {1}
    ids = [c.display_id for c in sim]
    assert len(set(ids)) == 74 and all(re.match(r"^SIM_([A-E]|Q[NSE])_\d{2}$", i) for i in ids)


def test_outlets_follow_d3_one_socket_per_berth_and_no_water_on_retrofit():
    for c in w.cabinets():
        slots = [c.outlets_for(i + 1) for i in range(len(c.berths))]
        sockets = [o for s in slots for o in s if o.startswith("Q")]
        assert len(sockets) == len(set(sockets)) == len(c.berths)   # one socket each, never shared
        if c.kind == "retrofit":
            assert not any(o.startswith("V") for s in slots for o in s)
    assert w.cabinets()[0].outlets_for(1) == ("Q1", "V1")             # A: long berths, Q1 3-phase


# ── values are functions ─────────────────────────────────────────────────────

def test_occupancy_is_between_70_and_85_percent_every_day():
    for d in range(w.day_of(T0) - 30, w.day_of(T0) + 30):
        share = len(w.occupied_set(SEED, d)) / 150
        assert 0.70 <= share <= 0.85, (d, share)


def test_boats_mostly_stay_more_than_a_day():
    d = w.day_of(T0)
    today, tomorrow = w.occupied_set(SEED, d), w.occupied_set(SEED, d + 1)
    assert len(today & tomorrow) / len(today) > 0.5


def test_the_same_seed_and_moment_give_the_same_answer_and_another_seed_does_not():
    b = w.berths()[0]
    assert w.register_kwh(SEED, b, T0) == w.register_kwh(SEED, b, T0)
    assert w.occupied_set(SEED, 50) == w.occupied_set(SEED, 50)
    assert w.occupied_set(SEED, 50) != w.occupied_set(SEED + 1, 50)


def test_a_meter_only_ever_rises_and_a_restart_changes_nothing():
    sample = [b for b in w.berths() if b.number in ("A-03", "C-11", "E-20", "QS-04")]
    end = T0 + timedelta(days=3)
    before = {}
    for b in sample:
        prev = None
        for i in range(0, 3 * 24 * 60, 7):            # three days, every 7 minutes
            e = w.register_kwh(SEED, b, T0 + timedelta(minutes=i))
            assert prev is None or e >= prev, (b.number, i, prev, e)
            prev = e
        before[b.number] = w.register_kwh(SEED, b, end)
    w._DAY_KWH.clear()                                  # "restart": nothing remembered
    assert {b.number: w.register_kwh(SEED, b, end) for b in sample} == before


def test_the_register_grows_by_the_power_it_reports():
    b = next(b for b in w.berths() if b.zone == "A" and w.plugged(SEED, b.number, T0))
    h0 = T0.replace(minute=0, second=0, microsecond=0)
    grow = w.register_kwh(SEED, b, h0 + timedelta(hours=1)) - w.register_kwh(SEED, b, h0)
    assert abs(grow - w.power_kw(SEED, b, h0)) < 1e-3


def test_wrong_vessel_and_power_without_vessel_happen_but_rarely():
    days = range(w.day_of(T0) - 30, w.day_of(T0))
    wrong = sum(w.wrong_vessel(SEED, b.number, w.EPOCH + w.DAY_TURN + timedelta(days=d, hours=3))
                for d in days for b in w.berths())
    pwv = sum((not w.occupied(SEED, b.number, t)) and w.plugged(SEED, b.number, t)
              for d in days for b in w.berths()
              for t in [w.EPOCH + w.DAY_TURN + timedelta(days=d, hours=3)])
    assert 0 < wrong < 0.06 * 150 * 30
    assert 0 < pwv < 0.05 * 150 * 30


def test_some_cabinet_raises_an_alarm_now_and_then():
    hits = sum(w.cabinet_alarm(SEED, c, w.EPOCH + timedelta(days=d, hours=h)) is not None
               for c in w.cabinets() for d in range(30, 60) for h in range(24))
    assert 0 < hits < 74 * 30 * 24 * 0.01


def test_every_day_at_least_one_simulated_berth_has_power_without_a_vessel():
    """v21 (T3): the demo always shows all six states."""
    real = {b.number for c in w.cabinets(include_real=True) if not c.simulated for b in c.berths}
    for day in range(60):
        t = w.EPOCH + w.DAY_TURN + timedelta(days=day, hours=3)
        pwv = [b.number for b in w.berths()
               if w.plugged(28, b.number, t) and not w.occupied(28, b.number, t)]
        assert pwv and not set(pwv) & real, day
        assert w.power_without_vessel_of_day(28, w.day_of(t)) in pwv
