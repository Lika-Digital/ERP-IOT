"""Write paths, run in a process whose local zone is UTC+14 (tests/test_utc_storage.py).

Not a test module: the test starts it with TZ set, then reads its one-line JSON
report. It drives the REAL write paths — HTTP routes, services, the collector,
the reconciler, the webhook receiver, retention — against a fresh SQLite
database and the cabinet simulator, then reads back every non-null DateTime
value in every table.

A value stored as local time is 14 hours away from UTC; the test allows 2.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="utc_scenario_"))
os.environ.update({
    "DATABASE_URL": f"sqlite:///{(TMP / 'utc.db').as_posix()}",
    "JWT_SECRET": "utc-scenario-secret",
    "ERP_ENCRYPTION_KEY": "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=",
    "COLLECTOR_ENABLED": "false",
})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from sqlalchemy import DateTime, select  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app import models as _models  # noqa: E402,F401 — every table
from simulator.cabinet_sim import create_app, iso_z, make_state, session_payload  # noqa: E402


def real_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ok(r, what):
    if r.status_code >= 400:
        raise SystemExit(f"scenario step failed: {what}: {r.status_code} {r.text[:300]}")
    return r


def main() -> dict:
    Base.metadata.create_all(bind=engine)
    local_offset_h = (datetime.now() - real_utc()).total_seconds() / 3600  # noqa: DTZ005

    state = make_state("full")
    state.service_email, state.service_password = "erp@utc.sim", "utc-sim-pass"
    state.contract = "r14"
    transport = httpx.ASGITransport(app=create_app(state))

    async def _no_sleep(_s):
        return None

    from app.services.pedestal_api_factory import get_pedestal_factory
    factory = get_pedestal_factory()
    factory.transport, factory.sleep = transport, _no_sleep

    with TestClient(app) as c:
        # D20: the first admin through the real path — one-time link, password,
        # 2FA enrolment (setup_tokens, auth_audit, users.totp_confirmed_at, last_login)
        import contextlib
        import io
        from app import setup_admin
        from app.utils import totp
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            setup_admin.main(["--email", "admin@utc.erp"])
        link_token = out.getvalue().split("#token=", 1)[1].split()[0]
        mfa = ok(c.post("/api/auth/setup", json={"token": link_token,
                                                 "password": "utc-admin-password"}),
                 "setup").json()["mfa_token"]
        mh = {"Authorization": f"Bearer {mfa}"}
        secret = ok(c.post("/api/auth/mfa/enroll/start", headers=mh), "enrol").json()["secret"]
        tok = ok(c.post("/api/auth/mfa/enroll/confirm", headers=mh,
                        json={"code": totp.code_at(secret, time.time())}),
                 "enrol confirm").json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        mid = ok(c.post("/api/marinas", headers=h, json={
            "name": "UTC", "location": "Krk", "timezone": "Europe/Zagreb",
            "pedestal_api_base_url": "http://sim.utc", "pedestal_service_email": "erp@utc.sim",
            "pedestal_service_password": "utc-sim-pass", "webhook_secret": "utc-hook"}),
            "marina").json()["id"]
        cab = ok(c.post(f"/api/marinas/{mid}/cabinets", headers=h, json={
            "pedestal_pk": 1, "display_id": "MAR_KRK_ORM_01", "device_type": "full",
            "erp_api_key": "sim-erp-key", "webhook_key": "utc-cabinet-hook"}),
            "cabinet").json()
        berth = ok(c.post(f"/api/marinas/{mid}/berth-registry", headers=h, json={
            "berth_number": "A-01", "cabinet_id": cab["id"], "cabinet_berth_id": 1}),
            "berth").json()
        ok(c.put(f"/api/marinas/{mid}/berth-registry/{berth['id']}/outlets", headers=h,
                 json={"outlets": ["Q1", "V1"]}), "mapping")
        ok(c.post(f"/api/marinas/{mid}/cabinets/{cab['id']}/nfc-tags/import",
                  headers={**h, "Content-Type": "text/csv"},
                  content="outlet,uid\nQ1,04A1B2C3D4E5F6\n"), "nfc import")
        ok(c.get(f"/api/marinas/{mid}/berths", headers=h), "berths")      # sync_log, cache
        ok(c.post(f"/api/marinas/{mid}/pedestals/1/outlets/Q1/cmd", headers=h,
                  json={"action": "stop", "reason": "utc scenario"}), "command")
        ok(c.post(f"/api/webhooks/cabinet/{cab['id']}", headers={"X-API-Key": "utc-cabinet-hook"},
                  json={"event": "hardware_alarm", "timestamp": iso_z(real_utc()),
                        "data": {"pedestal_id": 1, "alarm_type": "moisture", "id": 7}}),
           "webhook alarm")

        from app.models.billing import Customer
        from app.models.cabinet import Outlet
        from app.models.metering import ErpSession
        from app.services import credit
        db = SessionLocal()
        try:
            cust = Customer(marina_id=mid, external_ref="utc-user", full_name="UTC Guest")
            db.add(cust)
            db.commit()
            credit.post(db, customer_id=cust.id, delta="10.00", reason="topup",
                        created_by="reception@utc")
            q1 = db.query(Outlet).filter(Outlet.cabinet_id == cab["id"],
                                         Outlet.outlet_name == "Q1").one()
            db.add(ErpSession(erp_ref="erp-utc-1", cabinet_id=cab["id"], outlet_id=q1.id,
                              customer_id=cust.id, session_type="electricity",
                              status="active"))
            db.commit()
        finally:
            db.close()

        # the cabinet's times arrive with Z; they must land as the same instant in UTC
        state.nfc_sessions[501] = session_payload(
            session_id=501, socket_id="Q1", customer_id=None, erp_ref="erp-utc-1",
            status="ended", activated_at=iso_z(real_utc() - timedelta(minutes=40)),
            duration_minutes=30.0)
        ok(c.post(f"/api/webhooks/cabinet/{cab['id']}", headers={"X-API-Key": "utc-cabinet-hook"},
                  json={"event": "session_ended", "data": state.nfc_sessions[501]}),
           "webhook session")

        from app.services.collector import Collector
        col = Collector()
        asyncio.run(col.run_all_once())                  # seeds registers, reconciles
        # billed (phase 7 does this) — only a billed session is acknowledged (§4.0b, v8)
        db = SessionLocal()
        try:
            s = db.query(ErpSession).filter(ErpSession.erp_ref == "erp-utc-1").one()
            s.billing_state = "billed"
            db.commit()
        finally:
            db.close()
        state.sockets[0].energy_kwh += 0.5               # the next run: an interval, and the ack
        asyncio.run(col.run_all_once())                  # an interval
        from app.services import retention
        db = SessionLocal()
        try:
            retention.run(db)
        finally:
            db.close()

    # ── read back every stored time ─────────────────────────────────────────
    now = real_utc()
    # columns that are in the past ON PURPOSE, with how far (hours): the first
    # reconciliation looks back two days (reconciler.FIRST_LOOKBACK); later runs
    # start where the last one stopped
    expected_offset_h = {"reconciliation_runs.window_from": (-48.0, 0.0)}
    seen: dict = {}
    bad: list = []
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            cols = [col for col in table.columns if isinstance(col.type, DateTime)]
            if not cols:
                continue
            for row in conn.execute(select(*cols)):
                for col, v in zip(cols, row):
                    if v is None:
                        continue
                    if isinstance(v, str):
                        v = datetime.fromisoformat(v)
                    off_h = (v - now).total_seconds() / 3600
                    key = f"{table.name}.{col.name}"
                    seen[key] = seen.get(key, 0) + 1
                    if min(abs(off_h - e) for e in expected_offset_h.get(key, (0.0,))) > 2:
                        bad.append(f"{key} = {v.isoformat()} ({off_h:+.1f} h from UTC)")
    return {"local_offset_h": round(local_offset_h, 2), "seen": seen, "bad": bad}


if __name__ == "__main__":
    print("UTC_REPORT " + json.dumps(main()))
