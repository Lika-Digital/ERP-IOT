"""Phase 4 — collection, reconciliation, webhook, retention (spec §4.6, §4.7, §5.2, D7, D19).

Real collector, real reconciler, real client, against the simulator. Time is
moved with app.utils.time._simulated_clock where a test needs days to pass.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal

import pytest

from app.utils import time as erp_time
from simulator.cabinet_sim import iso_z, session_payload

WEBHOOK_KEY = "cabinet-webhook-key"
HMAC_SECRET = "cabinet-hmac-secret"


# ─── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def clock():
    """Move time: clock.now is naive UTC; clock.advance(seconds=…)."""
    class C:
        def __init__(self):
            self.now = erp_time.utcnow()

        def advance(self, **kw):
            self.now += timedelta(**kw)

    c = C()
    erp_time._simulated_clock = lambda: c.now
    try:
        yield c
    finally:
        erp_time._simulated_clock = None


@pytest.fixture
def cab(marina_id, sim):
    """A full cabinet with channel B and a webhook key, mapped like Krk."""
    from tests.conftest import TestSession, _clear_cabinets
    from app.services import cabinets as svc

    _clear_cabinets(marina_id)
    db = TestSession()
    try:
        c = svc.provision_cabinet(
            db, marina_id=marina_id, pedestal_pk=1, display_id="MAR_KRK_ORM_01",
            device_type="full", base_url="http://pedestal-sw.test",
            service_email="erp@test.service", service_password="test-service-pass-123",
            erp_api_key="sim-erp-key", webhook_key=WEBHOOK_KEY)
        for i, outs in {1: ["Q1"], 2: ["Q2"], 3: ["Q3", "V1"]}.items():
            b = svc.create_berth(db, marina_id=marina_id, berth_number=f"A-{i:02d}",
                                 cabinet_id=c.id, cabinet_berth_id=i)
            svc.set_berth_outlets(db, b, outs, assigned_by="test@lika.digital")
        cid = c.id
    finally:
        db.close()
    yield cid
    _clear_cabinets(marina_id)
    _wipe_logs()


def _wipe_logs():
    from tests.conftest import TestSession
    from app.models.billing import Customer
    from app.models.cache import AlarmLog, SessionLog, SyncLog
    db = TestSession()
    try:
        for m in (AlarmLog, SessionLog, SyncLog):
            db.query(m).delete()
        db.query(Customer).filter(Customer.external_ref.like("t-%")).delete(
            synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _db():
    from tests.conftest import TestSession
    return TestSession()


def _collector():
    from app.services.collector import Collector
    from tests.conftest import TestSession
    return Collector(session_factory=TestSession)


def _run(coro):
    return asyncio.run(coro)


def _intervals(cab_id):
    from app.models.cabinet import Outlet
    from app.models.metering import ConsumptionInterval
    db = _db()
    try:
        return (db.query(ConsumptionInterval, Outlet.outlet_name)
                .join(Outlet, Outlet.id == ConsumptionInterval.outlet_id)
                .filter(Outlet.cabinet_id == cab_id).order_by(ConsumptionInterval.id).all())
    finally:
        db.close()


def _erp_session(cab_id, outlet="Q1", ref="erp-1", customer_ref="t-guest-7", status="reserved"):
    from app.models.billing import Customer
    from app.models.cabinet import Cabinet, Outlet
    from app.models.metering import ErpSession
    db = _db()
    try:
        cab = db.get(Cabinet, cab_id)
        cust = db.query(Customer).filter(Customer.external_ref == customer_ref).first()
        if cust is None:
            cust = Customer(marina_id=cab.marina_id, external_ref=customer_ref, full_name="Gost")
            db.add(cust)
            db.flush()
        o = db.query(Outlet).filter(Outlet.cabinet_id == cab_id,
                                    Outlet.outlet_name == outlet).one()
        s = ErpSession(erp_ref=ref, cabinet_id=cab_id, outlet_id=o.id, customer_id=cust.id,
                       session_type="water" if outlet.startswith("V") else "electricity",
                       status=status)
        db.add(s)
        db.commit()
        return s.id
    finally:
        db.close()


def _get(model, pk):
    db = _db()
    try:
        return db.get(model, pk)
    finally:
        db.close()


# ─── health -> cabinet state ─────────────────────────────────────────────────

def test_health_sets_smart_mode_and_heartbeat_as_naive_utc(sim, cab):
    from app.models.cabinet import Cabinet
    _run(_collector().run_all_once())
    c = _get(Cabinet, cab)
    assert c.smart_mode is True
    assert c.last_heartbeat_at is not None and c.last_heartbeat_at.tzinfo is None
    assert abs((erp_time.utcnow() - c.last_heartbeat_at).total_seconds()) < 60
    sim.state.sim.smart_mode = False
    _run(_collector().run_all_once())
    assert _get(Cabinet, cab).smart_mode is False


# ─── load -> intervals (§4.6, D10) ───────────────────────────────────────────

def test_register_differences_become_intervals_and_idle_is_one_row(sim, cab, clock):
    col = _collector()
    st = sim.state.sim
    _run(col.run_all_once())                         # seeds the registers
    assert _intervals(cab) == []
    clock.advance(minutes=5)
    st.sockets[0].energy_kwh += 0.75                 # Q1 consumed 0.75 kWh
    _run(col.run_all_once())
    rows = {name: iv for iv, name in _intervals(cab)}
    assert rows["Q1"].energy_kwh == Decimal("0.7500")
    assert (rows["Q1"].meter_from, rows["Q1"].meter_to) == (Decimal("1200.0000"),
                                                            Decimal("1200.7500"))
    assert rows["Q1"].source == "register" and rows["Q1"].session_id is None
    n = len(_intervals(cab))
    for _ in range(5):                               # five idle polls
        clock.advance(minutes=5)
        _run(col.run_all_once())
    q2 = [iv for iv, name in _intervals(cab) if name == "Q2"]
    assert len(_intervals(cab)) == n + 1, "idle Q1 got rows: zero must extend, not add"
    assert len(q2) == 1 and q2[0].energy_kwh == 0
    assert q2[0].to_at - q2[0].from_at == timedelta(minutes=30)


def test_a_register_going_backwards_is_never_a_negative_interval(sim, cab, clock):
    col = _collector()
    _run(col.run_all_once())
    clock.advance(minutes=5)
    sim.state.sim.sockets[0].energy_kwh = 3.0        # meter swapped
    _run(col.run_all_once())
    assert all(iv.energy_kwh >= 0 for iv, _ in _intervals(cab))
    clock.advance(minutes=5)
    sim.state.sim.sockets[0].energy_kwh = 3.5
    _run(col.run_all_once())
    q1 = [iv for iv, n in _intervals(cab) if n == "Q1"]
    assert [iv.energy_kwh for iv in q1] == [Decimal("0.5000")]   # from the new meter on


def test_d19_smart_mode_off_consumption_is_standalone_and_never_on_a_session(sim, cab, clock):
    from app.models.metering import ErpSession
    sid = _erp_session(cab, status="active")
    col = _collector()
    _run(col.run_all_once())
    clock.advance(minutes=1)
    sim.state.sim.sockets[0].energy_kwh += 0.2       # Smart Mode ON: the ERP's session
    _run(col.run_all_once())
    sim.state.sim.smart_mode = False
    clock.advance(minutes=1)
    _run(col.run_all_once())                         # health reads OFF
    clock.advance(minutes=1)
    sim.state.sim.sockets[0].energy_kwh += 0.3       # standalone use
    _run(col.run_all_once())
    q1 = [iv for iv, n in _intervals(cab) if n == "Q1" and iv.energy_kwh > 0]
    assert [(iv.energy_kwh, iv.session_id, iv.standalone) for iv in q1] == [
        (Decimal("0.2000"), sid, False), (Decimal("0.3000"), None, True)]
    assert _get(ErpSession, sid).status == "active"  # nothing billed off the standalone part


def test_load_is_polled_every_60_s_when_busy_and_every_300_s_when_idle(sim, cab, clock):
    col = _collector()
    _run(col.run_all_once())

    def load_calls():
        return len([c for c in sim.state.sim.calls if c[1].endswith("/load")])

    base = load_calls()
    for _ in range(4):
        clock.advance(seconds=60)
        _run(col.tick())
    assert load_calls() == base, "idle cabinet polled more often than every 300 s"
    clock.advance(seconds=60)
    _run(col.tick())
    assert load_calls() == base + 1
    sim.state.sim.sockets[1].current = 8.0           # someone plugs in
    sim.state.sim.sockets[1].power_kw = 1.8
    clock.advance(seconds=300)
    _run(col.tick())
    base = load_calls()
    for _ in range(3):
        clock.advance(seconds=60)
        _run(col.tick())
    assert load_calls() == base + 3
    sim.state.sim.sockets[1].current = 0.0           # unplugged: back to every 300 s
    sim.state.sim.sockets[1].power_kw = 0.0
    clock.advance(seconds=60)
    _run(col.tick())
    base = load_calls()
    for _ in range(4):
        clock.advance(seconds=60)
        _run(col.tick())
    assert load_calls() == base


def test_polled_alarms_are_stored_once(sim, cab):
    from app.models.cache import AlarmLog
    sim.state.sim.alarms = [{"id": 31, "alarm_type": "moisture", "pedestal_id": 1,
                             "status": "triggered"}]
    col = _collector()
    _run(col.run_all_once())
    _run(col.run_all_once())
    db = _db()
    try:
        rows = db.query(AlarmLog).filter(AlarmLog.cabinet_id == cab).all()
    finally:
        db.close()
    assert [(r.cabinet_alarm_id, r.source) for r in rows] == [(31, "poll")]


# ─── reconciliation, today's cabinet (a709cf8): by-user ──────────────────────

def test_reconcile_on_todays_cabinet_falls_back_to_by_user_and_links_the_session(sim, cab):
    from app.models.metering import ErpSession, ReconciliationRun
    sid = _erp_session(cab, outlet="Q1", customer_ref="t-guest-7")
    sim.state.sim.nfc_sessions[101] = session_payload(
        session_id=101, socket_id="Q1", customer_id="t-guest-7", status="ended")
    # a session the ERP never started (Smart Mode OFF, D19): not imported
    sim.state.sim.nfc_sessions[102] = session_payload(
        session_id=102, socket_id="Q2", customer_id="t-guest-7", status="ended")
    _run(_collector().run_all_once())
    s = _get(ErpSession, sid)
    assert (s.cabinet_session_id, s.status, s.energy_kwh) == (101, "ended", Decimal("3.2500"))
    assert s.consumption_source == "register" and s.recompute_ok is True
    assert s.reconciled_at is not None and s.billing_state == "pending"
    db = _db()
    try:
        run = db.query(ReconciliationRun).filter_by(cabinet_id=cab).one()
        assert db.query(ErpSession).filter_by(cabinet_id=cab).count() == 1
    finally:
        db.close()
    assert (run.mode, run.ok, run.sessions_seen, run.sessions_updated,
            run.sessions_unknown) == ("by_user", True, 2, 1, 1)
    assert ("GET", "/api/nfc/sessions/by-user/t-guest-7") in sim.state.sim.calls


def test_reconcile_without_channel_b_key_is_a_failed_run_with_the_reason(sim, cab):
    from app.models.cabinet import Cabinet
    from app.models.metering import ReconciliationRun
    db = _db()
    try:
        db.get(Cabinet, cab).erp_api_key_enc = None
        db.commit()
        _run(_collector().run_all_once())
        run = db.query(ReconciliationRun).filter_by(cabinet_id=cab).one()
    finally:
        db.close()
    assert not run.ok and "X-API-Key" in run.error


# ─── reconciliation, R14 b/c ─────────────────────────────────────────────────

def test_r14_range_matches_by_erp_ref_acks_only_billed_and_reads_change_nothing(sim, cab,
                                                                                   clock):
    from app.models.metering import ErpSession, ReconciliationRun
    st = sim.state.sim
    st.contract = "r14"
    sid = _erp_session(cab, outlet="V1", ref="erp-r14-1", customer_ref="t-r14")
    started = clock.now - timedelta(minutes=40)
    st.nfc_sessions[201] = session_payload(
        session_id=201, socket_id="V1", session_type="water", customer_id=None,
        erp_ref="erp-r14-1", activated_at=iso_z(started), duration_minutes=30.0,
        energy_kwh=None, meter_energy_start_kwh=None, meter_energy_end_kwh=None,
        water_liters=120.0, meter_water_start_l=500.0, meter_water_end_l=620.0)
    _run(_collector().run_all_once())
    s = _get(ErpSession, sid)
    assert (s.cabinet_session_id, s.water_liters, s.reconciled_at is not None) == (
        201, Decimal("120.000"), True)
    assert s.ended_at == started + timedelta(minutes=30)   # activated_at + duration
    # reconciled is not billed: no ack yet (the cabinet's contract, eac7aa2 nfc.py:950-968)
    assert s.ack_sent_at is None and st.acked == []
    assert st.reconciled == {}, "a read changed state on the cabinet"
    db = _db()
    try:
        run = db.query(ReconciliationRun).filter_by(cabinet_id=cab).one()
    finally:
        db.close()
    assert (run.mode, run.ok, run.sessions_acked) == ("range", True, 0)
    assert run.window_to == clock.now

    # billed (phase 7 does this) -> the next run acks it, once
    db = _db()
    try:
        db.get(ErpSession, sid).billing_state = "billed"
        db.commit()
    finally:
        db.close()
    # the next run continues where this one stopped, with the overlap
    clock.advance(minutes=15)
    col = _collector()
    _run(col.run_all_once())
    db = _db()
    try:
        r2 = (db.query(ReconciliationRun).filter_by(cabinet_id=cab)
              .order_by(ReconciliationRun.id.desc()).first())
    finally:
        db.close()
    assert r2.window_from == run.window_to - timedelta(minutes=10)
    assert st.acked == [201] and _get(ErpSession, sid).ack_sent_at is not None
    clock.advance(minutes=15)
    _run(_collector().run_all_once())
    assert st.acked == [201], "acked twice"


def test_r14_range_reads_every_page(sim, cab, clock, monkeypatch):
    from app.services import reconciler
    from app.models.metering import ErpSession
    monkeypatch.setattr(reconciler, "PAGE", 2)
    st = sim.state.sim
    st.contract = "r14"
    ids = []
    for i in range(5):
        ids.append(_erp_session(cab, outlet="Q1", ref=f"erp-p{i}", customer_ref="t-p",
                                status="active" if i == 4 else "reserved"))
        st.nfc_sessions[300 + i] = session_payload(
            session_id=300 + i, socket_id="Q1", customer_id=None, erp_ref=f"erp-p{i}",
            activated_at=iso_z(clock.now - timedelta(hours=3 - i * 0.1)))
    _run(_collector().run_all_once())
    assert all(_get(ErpSession, i).reconciled_at is not None for i in ids)
    pages = [c for c in st.calls if c == ("GET", "/api/nfc/sessions")]
    assert len(pages) == 3


# ─── webhook receiver (§5.2) ─────────────────────────────────────────────────

def _hook(client, cab_id, body, key=WEBHOOK_KEY, sig=None):
    raw = json.dumps(body).encode()
    h = {"Content-Type": "application/json"}
    if key is not None:
        h["X-API-Key"] = key
    if sig:
        h["X-Webhook-Signature"] = sig
    return client.post(f"/api/webhooks/cabinet/{cab_id}", content=raw, headers=h)


@pytest.mark.parametrize("who", ["no_key", "empty_key", "wrong_key", "unknown_cabinet"])
def test_webhook_refuses_without_the_cabinets_key_all_the_same_way(client, cab, who):
    body = {"event": "hardware_alarm", "data": {"id": 1}, "timestamp": "x"}
    r = {"no_key": lambda: _hook(client, cab, body, key=None),
         "empty_key": lambda: _hook(client, cab, body, key=""),
         "wrong_key": lambda: _hook(client, cab, body, key="guess"),
         "unknown_cabinet": lambda: _hook(client, 99999, body)}[who]()
    assert (r.status_code, r.json()["detail"]) == (401, "Invalid or missing webhook credentials")


def test_webhook_from_a_cabinet_without_a_stored_key_is_refused(client, cabinet_config,
                                                                 marina_id):
    cid = cabinet_config(marina_id, "full", {"1": ["Q1"]})       # provisioned with no key
    r = _hook(client, cid, {"event": "hardware_alarm", "data": {}}, key="")
    assert r.status_code == 401


def test_webhook_hmac_switch_requires_a_valid_signature(client, cab):
    from app.models.cabinet import Cabinet
    from app.utils.encryption import encrypt_password
    db = _db()
    try:
        c = db.get(Cabinet, cab)
        c.webhook_secret_enc, c.webhook_hmac = encrypt_password(HMAC_SECRET), True
        db.commit()
    finally:
        db.close()
    body = {"event": "hardware_alarm", "data": {}, "timestamp": "x"}
    assert _hook(client, cab, body).status_code == 401              # key alone is not enough
    raw = json.dumps(body).encode()
    sig = "sha256=" + hmac.new(HMAC_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    assert _hook(client, cab, body, sig=sig).status_code == 200
    assert _hook(client, cab, body, sig="sha256=" + "0" * 64).status_code == 401


def test_webhook_body_is_capped(client, cab):
    r = _hook(client, cab, {"event": "hardware_alarm", "data": {"x": "a" * 70000}})
    assert r.status_code == 413


def test_webhook_session_is_fast_but_only_the_pull_reconciles(client, sim, cab):
    """D7: the webhook updates the ERP session at once — through the same function as the
    pull — but never marks it reconciled; billing waits for the pull."""
    from app.models.cache import SessionLog
    from app.models.metering import ErpSession
    sid = _erp_session(cab, outlet="Q1", customer_ref="t-wh")
    p = session_payload(session_id=111, socket_id="Q1", customer_id="t-wh", status="ended")
    r = _hook(client, cab, {"event": "session_ended", "data": p, "timestamp": "x"})
    assert r.status_code == 200 and "updated" in r.json()["stored"]
    s = _get(ErpSession, sid)
    assert (s.cabinet_session_id, s.status, s.reconciled_at) == (111, "ended", None)
    db = _db()
    try:
        assert db.query(SessionLog).count() == 1
    finally:
        db.close()
    sim.state.sim.nfc_sessions[111] = p
    _run(_collector().run_all_once())
    assert _get(ErpSession, sid).reconciled_at is not None


@pytest.mark.parametrize("body, why", [
    ({"event": "session_ended", "session_id": 7, "status": "ended"}, "no data object"),  # today's flat shape
    ({"event": "session_completed", "data": {"session_id": 7}}, "unknown event"),         # old ERP name
    ({"event": "heartbeat", "data": {}}, "unknown event"),
    ({"event": "telemetry", "data": {"energy_kwh": 1.0}}, "session event without session_id in data"),
    ({"data": {}}, "no event"),
])
def test_webhook_of_an_unknown_shape_is_refused_and_recorded(client, cab, body, why):
    """v21 (§2.6): no tolerant parsing — refused with 422, recorded in sync_log by its
    shape (event and keys), never by its content. The pull stays the truth (D7)."""
    from app.models.cache import SyncLog
    r = _hook(client, cab, body)
    assert r.status_code == 422 and r.json()["detail"]["reason"] == why
    db = _db()
    try:
        row = (db.query(SyncLog).filter(SyncLog.sync_type == "webhook.cabinet")
               .order_by(SyncLog.id.desc()).first())
        assert row.status == "error" and row.error_message.startswith(why)
        assert "ended\"" not in row.error_message and "1.0" not in row.error_message
    finally:
        db.close()


def test_webhook_alarm_and_poll_alarm_are_one_row(client, sim, cab):
    from app.models.cache import AlarmLog
    r = _hook(client, cab, {"event": "hardware_alarm",
                            "data": {"id": 55, "pedestal_id": 1, "alarm_type": "moisture"}})
    assert r.json()["stored"] == "alarm_log"
    sim.state.sim.alarms = [{"id": 55, "pedestal_id": 1, "status": "triggered"}]
    _run(_collector().run_all_once())
    r = _hook(client, cab, {"event": "hardware_alarm", "data": {"id": 55}})
    assert r.json()["stored"] == "alarm_log: already known"
    db = _db()
    try:
        assert db.query(AlarmLog).filter_by(cabinet_id=cab, cabinet_alarm_id=55).count() == 1
    finally:
        db.close()


def test_old_marina_webhook_fails_closed_without_a_secret(client, restricted_marina_id):
    r = client.post(f"/api/webhooks/pedestal/{restricted_marina_id}",
                    json={"event_type": "alarm", "pedestal_id": 1})
    assert r.status_code == 401


# ─── retention (§4.7, D7) ────────────────────────────────────────────────────

def test_retention_deletes_by_window_and_rolls_intervals_into_months(cab):
    from app.config import settings
    from app.models.cabinet import Outlet
    from app.models.cache import SyncLog
    from app.models.metering import ConsumptionInterval, ConsumptionMonthly
    from app.services import retention
    now = erp_time.utcnow()
    db = _db()
    try:
        q1 = db.query(Outlet).filter_by(cabinet_id=cab, outlet_name="Q1").one()
        # 10:00 that day: three hourly rows must never straddle a month boundary
        old = (now - timedelta(days=settings.retention_intervals_days + 40)).replace(
            hour=10, minute=0, second=0, microsecond=0)
        for i, kwh in enumerate(("1.25", "2.50", "0.25")):
            f = old + timedelta(hours=i)
            db.add(ConsumptionInterval(outlet_id=q1.id, from_at=f, to_at=f + timedelta(hours=1),
                                       energy_kwh=Decimal(kwh), source="register"))
        db.add(ConsumptionInterval(outlet_id=q1.id, from_at=now - timedelta(hours=1), to_at=now,
                                   energy_kwh=Decimal("9"), source="register"))
        for days in (settings.retention_sync_log_days + 1, 1):
            t = now - timedelta(days=days)
            db.add(SyncLog(marina_id=1, sync_type="x", status="success", started_at=t))
        db.commit()
        out = retention.run(db, now)
        assert out["consumption_intervals"] == 3 and out["sync_log"] >= 1
        [m] = db.query(ConsumptionMonthly).filter_by(outlet_id=q1.id).all()
        assert (m.energy_kwh, m.interval_count, m.standalone) == (Decimal("4.0000"), 3, False)
        assert db.query(ConsumptionInterval).filter_by(outlet_id=q1.id).count() == 1
        assert db.query(SyncLog).filter(SyncLog.started_at < now - timedelta(days=30)).count() == 0
        assert db.query(SyncLog).filter(SyncLog.sync_type == "x").count() == 1
        assert retention.run(db, now)["consumption_intervals"] == 0   # idempotent
        db.query(ConsumptionMonthly).filter_by(outlet_id=q1.id).delete()
        db.commit()
    finally:
        db.close()


def test_every_growing_table_has_a_window_or_is_named_as_kept():
    """A table that grows without a retention rule is how the database fills up (D7).
    Every table is either in retention.windows(), rolled up, or named here as kept."""
    from app.database import Base
    import app.models  # noqa: F401
    from app.services import retention
    kept_on_purpose = {
        # accounting — permanent (§4.7)
        "sessions", "credit_ledger", "billing_records",
        # one row per thing, updated in place
        "users", "user_marina_access", "marinas", "cabinets", "cabinet_capabilities", "outlets",
        "berths", "berth_outlets", "berth_outlets_cabinet", "mapping_comparison",
        "outlet_nfc_tags", "outlet_meter_state", "customers", "contracts", "tariffs",
        "marina_billing_policy",
        # D20: at most ten per user, replaced as a set (spec §4.9)
        "user_backup_codes",
        # tiny aggregate
        "consumption_monthly",
        # D21: files an Admin imported on purpose; one row per agent rule
        "admin_imports", "security_rule_settings",
        # D27 phase 1: one row per vessel, one per change of a berth's vessel. How long a
        # PAST owner's data is kept is open (spec O67) — not decided here
        "vessels", "berth_vessels",
    }
    managed = set(retention.windows()) | {"consumption_intervals"}
    tables = set(Base.metadata.tables)
    assert tables - managed - kept_on_purpose == set()
    assert managed & kept_on_purpose == set()


# ─── O31: the client comes from the cabinet row ──────────────────────────────

def test_client_is_built_from_the_cabinet_not_the_marina(marina_id, cabinet_config, sim):
    from app.models.cabinet import Cabinet
    from app.services.pedestal_api_factory import get_pedestal_factory
    cid = cabinet_config(marina_id, "full", {"1": ["Q1"]})
    db = _db()
    try:
        c = db.get(Cabinet, cid)
        c.base_url = "http://cabinet-1.tailnet.test"
        db.commit()
        client = get_pedestal_factory().get_client(marina_id, db)
    finally:
        db.close()
    assert client.base_url == "http://cabinet-1.tailnet.test"


def test_health_reports_the_collector(client):
    body = client.get("/api/health").json()
    assert set(body["collector"]) >= {"enabled", "running", "role", "cycles"}
    assert body["collector"]["enabled"] is False     # COLLECTOR_ENABLED=false in tests


def test_sync_log_records_changes_not_every_successful_poll(sim, cab):
    """Phase 4: a row per successful call was 10 400 rows a day for two cabinets.
    Now: errors and stale every time, success only first / after a failure."""
    from app.models.cache import SyncLog
    from app.services.pedestal_api_factory import get_pedestal_factory
    db = _db()
    try:
        from app.models.cabinet import Cabinet
        client = get_pedestal_factory().for_cabinet(db.get(Cabinet, cab))
        for _ in range(5):
            _run(client.health(db))
        sim.state.sim.fail_next = [500, 500, 500]
        _run(client.health(db))                          # error (+ stale from the cache)
        for _ in range(5):
            _run(client.health(db))                      # recovered
        rows = [r.status for r in db.query(SyncLog).filter(SyncLog.sync_type ==
                                                           "pedestals.health")
                .order_by(SyncLog.id)]
    finally:
        db.close()
    assert rows == ["success", "error", "stale", "success"]


def test_a_slow_collector_never_makes_the_api_wait(client):
    """§4.0b: the collector's database work is synchronous and a cabinet can take
    seconds; it runs on its own thread and loop, so an operator's request does not wait."""
    import time
    from pathlib import Path
    from app.services.collector import Collector, CollectorThread

    class Slow(Collector):
        async def tick(self, force_nightly=False):
            time.sleep(1.5)            # blocking, like a long sync query or a hung cabinet
            return {}

    w = CollectorThread(Slow(session_factory=_db))
    w.start()
    try:
        time.sleep(0.2)                # the slow tick is under way
        t0 = time.monotonic()
        r = client.get("/api/health")
        waited = time.monotonic() - t0
    finally:
        w.stop()
    assert r.status_code == 200 and waited < 1.0, f"the API waited {waited:.2f} s"
    main = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    assert "CollectorThread(collector)" in main, "the app must start the collector on its thread"


def test_new_contract_session_without_erp_ref_is_not_ours_not_a_broken_payload(sim, cab):
    """Cabinet eac7aa2: the payload has `erp_ref` instead of `customer_id`, and erp_ref is
    null for a session the ERP did not start (Smart Mode OFF, D19). That is 'unknown',
    never a contract break."""
    from app.services import session_sync
    from app.models.cabinet import Cabinet
    raw = session_payload(session_id=777, socket_id="Q2", erp_ref=None)
    del raw["customer_id"]
    db = _db()
    try:
        out = session_sync.apply(db, db.get(Cabinet, cab), raw, final_by_pull=True,
                                 now=erp_time.utcnow())
    finally:
        db.close()
    assert out == "unknown"
