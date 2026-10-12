"""Pure contract logic, no HTTP: session payload, NFC UIDs, berth status table.

The same behaviours are exercised end-to-end against the simulator in
test_cabinet_sim.py (TC-ERP-SIM-*). Here each rule is pinned on its own, so a
failure names the rule and not "the simulator test broke".
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.cabinet import berth_status as bs
from app.cabinet.nfc_uid import UidError, both_forms, find_tag, normalise
from app.cabinet.session_payload import (
    CONTRACT_KEYS, PRICE_KEYS, PayloadError, parse_session,
)


def _session(**over):
    base = {
        "session_id": 41, "cabinet_id": "MAR_KRK_ORM_01", "socket_id": "Q1",
        "session_type": "electricity", "customer_id": "u-7", "status": "ended",
        "activated_at": "2026-10-11T07:00:00Z", "duration_minutes": 95.0,
        "energy_kwh": 3.25, "water_liters": None,
        "meter_energy_start_kwh": 1200.50, "meter_energy_end_kwh": 1203.75,
        "meter_water_start_l": None, "meter_water_end_l": None,
        "consumption_source": "register", "power_kw_current": None,
    }
    base.update(over)
    return base


def _walk(obj):
    """Every key and every value, recursively — to prove ABSENCE of a field."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk(v)
    else:
        yield obj


# ─── session payload ──────────────────────────────────────────────────────────

def test_contract_has_exactly_16_keys():
    assert len(CONTRACT_KEYS) == 16


def test_clean_register_session_is_billable():
    p = parse_session(_session())
    assert p.billable and not p.manual_review and p.findings == ()
    assert p.consumption == 3.25 and p.unit == "kWh"


@pytest.mark.parametrize("price_key", sorted(PRICE_KEYS))
def test_price_field_is_absent_after_parsing(price_key):
    p = parse_session(_session(**{price_key: 12.34}))
    d = p.to_dict()
    assert price_key not in set(_walk(d)) - {"price_field_dropped"}
    assert not hasattr(p, price_key)
    assert 12.34 not in set(_walk(d)), "the price VALUE leaked into the parsed session"
    assert any(f.code == "price_field_dropped" for f in p.findings)


def test_water_session_is_attributed_to_v1_never_q1():
    p = parse_session(_session(
        socket_id="V1", session_type="water", energy_kwh=None, water_liters=40.0,
        meter_energy_start_kwh=None, meter_energy_end_kwh=None,
        meter_water_start_l=500.0, meter_water_end_l=540.0,
    ))
    assert p.outlet_name == "V1" and p.unit == "L" and p.consumption == 40.0


@pytest.mark.parametrize("bad", [1, "1", "Q5", "V3", "q1"])
def test_bare_or_unknown_outlet_is_refused(bad):
    with pytest.raises(PayloadError):
        parse_session(_session(socket_id=bad))


def test_outlet_prefix_must_match_session_type():
    with pytest.raises(PayloadError):
        parse_session(_session(socket_id="V1"))  # electricity on a valve


def test_recompute_mismatch_is_a_finding_and_not_billable():
    p = parse_session(_session(energy_kwh=4.00))   # registers say 3.25
    assert p.manual_review and not p.billable
    assert any(f.code == "recompute_mismatch" for f in p.findings)


def test_null_figure_is_review_never_zero():
    p = parse_session(_session(energy_kwh=None, consumption_source="unknown",
                               meter_energy_end_kwh=None))
    assert p.consumption is None
    assert p.manual_review and not p.billable
    codes = {f.code for f in p.findings}
    assert {"figure_null", "measurement_missing"} <= codes


def test_null_on_an_active_session_is_not_a_finding():
    p = parse_session(_session(status="active", energy_kwh=None, consumption_source=None,
                               meter_energy_end_kwh=None))
    assert not p.manual_review and not p.billable


def test_power_null_stays_null():
    assert parse_session(_session(power_kw_current=None)).power_kw_current is None
    assert parse_session(_session(power_kw_current=0.0)).power_kw_current == 0.0


def test_missing_contract_key_is_a_contract_break():
    raw = _session()
    del raw["meter_energy_start_kwh"]
    with pytest.raises(PayloadError, match="meter_energy_start_kwh"):
        parse_session(raw)


# ─── NFC UID (TC-ERP-SIM-14) ──────────────────────────────────────────────────

class _Tag:
    def __init__(self, primary, outlet):
        self.uid_primary, self.uid_reversed = both_forms(primary)
        self.outlet = outlet


def test_uid_both_forms():
    assert both_forms("35:b2:5a:04:09:01:04:e0") == (
        "35:B2:5A:04:09:01:04:E0", "E0:04:01:09:04:5A:B2:35")


@pytest.mark.parametrize("scanned", [
    "35:B2:5A:04:09:01:04:E0",   # primary
    "E0:04:01:09:04:5A:B2:35",   # reversed
    "e004010904 5ab235",         # reversed, phone formatting
])
def test_tag_found_by_either_form_and_points_at_the_exact_outlet(scanned):
    tags = [_Tag("35:B2:5A:04:09:01:04:E0", "Q2"), _Tag("11:22:33:44:55:66:77:88", "V1")]
    assert find_tag(scanned, tags).outlet == "Q2"


def test_bad_uid_is_an_error_not_a_miss():
    with pytest.raises(UidError):
        normalise("35:B2:5")


# ─── berth status table (§3.2) ────────────────────────────────────────────────

# naive UTC, the same contract as app.utils.time.utcnow() and the DB columns
NOW = datetime(2026, 10, 12, 10, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)


def _sig(**over):
    base = dict(now=NOW, last_heartbeat=NOW - timedelta(seconds=20), smart_mode=True,
                state_code=0, last_analyzed=NOW - timedelta(minutes=5))
    base.update(over)
    return bs.BerthSignals(**base)


def test_free_berth():
    r = bs.compute(_sig())
    assert (r.status_code, r.status, r.berth_colour) == ("free", "ok", "green")


def test_silent_cabinet_is_grey_even_if_retained_state_looks_healthy():
    r = bs.compute(_sig(last_heartbeat=NOW - timedelta(minutes=11), state_code=1))
    assert (r.status_code, r.berth_colour, r.connection) == ("no_contact", "grey", "OFFLINE")


def test_stale_cache_travels_to_the_colour():
    r = bs.compute(_sig(data_is_stale=True, data_synced_at=NOW - timedelta(minutes=3),
                        state_code=1))
    assert (r.status_code, r.berth_colour) == ("no_contact", "grey")
    assert r.data_as_of == "09:57"


def test_standalone_is_unknown_not_attention():
    r = bs.compute(_sig(smart_mode=False, water_leak=True))
    assert (r.status_code, r.status) == ("standalone", "unknown")


def test_highest_rank_wins():
    r = bs.compute(_sig(water_leak=True, breaker_tripped=True, state_code=2))
    assert r.status_code == "water_leak"


def test_vessel_unknown_is_never_drawn_free():
    r = bs.compute(_sig(last_analyzed=NOW - timedelta(minutes=31)))
    assert (r.status_code, r.berth_colour, r.vessel) == ("unclassified", "grey", "UNKNOWN")


def test_power_without_vessel_needs_both_signals():
    assert bs.compute(_sig(power_active=True)).status_code == "power_without_vessel"
    assert bs.compute(_sig(power_active=None)).status_code == "free"


def test_stale_connection_is_a_signal_not_a_status():
    r = bs.compute(_sig(last_heartbeat=NOW - timedelta(minutes=3)))
    assert r.connection == "STALE" and r.status_code == "free"


def test_every_row_has_a_distinct_code():
    codes = [row[1] for row in bs._TABLE]
    assert len(codes) == len(set(codes)) == 13
