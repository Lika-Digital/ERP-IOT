"""Phase 4 exit criterion: database growth MEASURED and BOUNDED (spec §10, D7).

Runs the real collector, the real reconciler, the real webhook receiver and
real retention against two simulated Krk cabinets, through simulated days,
and reports the database before and after:

  day 0 (provisioned, nothing collected)  ->  day N (default 7)

per table: rows, bytes (PostgreSQL: pg_total_relation_size; SQLite: only the
file), rows per day. From the measured rate and the retention window of each
table (app/config.py) it computes the ceiling each table converges to. Then it
PROVES the ceiling: the clock jumps past every window and retention runs —
windowed tables must empty, intervals must roll into the monthly aggregate
with the same kWh, accounting tables must stay.

It fails (exit 1) if retention does not hold, or the projected database
exceeds BUDGET_MB.

What it is not: a week on a real cabinet. The cabinets are simulators, the
clock is simulated, the traffic is a modelled Krk day (below). The real week
is measured on the VPS after phase 5 (spec §11 O35).

Usage:  backend/.venv/Scripts/python.exe scripts/growth_check.py [--days 7]
Env:    GROWTH_DATABASE_URL  optional (CI: PostgreSQL); default a temp SQLite file
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
BUDGET_MB = 1024          # the pilot's steady state; the VPS disk is 20 GB (§8.2)

# A modelled Krk day, per cabinet (Smart Mode ON unless said):
SESSIONS_PER_DAY = [(8, "Q1"), (11, "Q2"), (15, "Q3"), (19, "Q4")]   # 90 min, 2.3 kW each
SESSION_MIN = 90
STANDALONE = (13, "Q2", 60)        # cabinet 2: Smart Mode OFF 13:00-14:00, Q2 in use
ALARMS_PER_DAY = 1


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="growth_"))
    db_url = os.environ.get("GROWTH_DATABASE_URL") or f"sqlite:///{(tmp / 'growth.db').as_posix()}"
    os.environ.update({
        "DATABASE_URL": db_url, "JWT_SECRET": "growth-check-" + os.urandom(6).hex(),
        "DEFAULT_ADMIN_EMAIL": "growth@check.erp", "DEFAULT_ADMIN_PASSWORD": "growth-pass",
        "ERP_ENCRYPTION_KEY": "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=",
        "COLLECTOR_ENABLED": "false",
    })
    sys.path.insert(0, str(BACKEND))
    os.chdir(BACKEND)

    import subprocess
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=str(BACKEND),
                       capture_output=True, text=True, env=os.environ.copy())
    if r.returncode != 0:
        print(r.stderr[-2000:])
        return 1

    import httpx
    from sqlalchemy import func, inspect, text
    from starlette.testclient import TestClient

    import logging
    from sqlalchemy import event

    from app.config import settings
    from app.database import SessionLocal, engine
    # speed of the measurement, not of the product: no per-request log lines, and on
    # SQLite no fsync per commit (the row counts and sizes are the same)
    for name in ("httpx", "app", "uvicorn"):
        logging.getLogger(name).setLevel(logging.WARNING)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def _fast(dbapi_conn, _rec):
            dbapi_conn.execute("PRAGMA synchronous=OFF")
            dbapi_conn.execute("PRAGMA journal_mode=MEMORY")
        engine.dispose()
    from app.main import app as erp_app
    from app.models.billing import Customer
    from app.models.cabinet import Outlet
    from app.models.metering import ConsumptionInterval, ConsumptionMonthly, ErpSession
    from app.services import cabinets as svc
    from app.services import retention
    from app.services.collector import Collector
    from app.services.pedestal_api_factory import get_pedestal_factory
    from app.utils import time as erp_time
    from simulator.cabinet_sim import _berth, create_app, iso_z, make_state, session_payload

    start = datetime(2026, 11, 2, tzinfo=timezone.utc).replace(tzinfo=None)  # a Monday
    clock = {"now": start}
    erp_time._simulated_clock = lambda: clock["now"]

    # ── two cabinets, two cabinet servers ─────────────────────────────────────
    states, apps = {}, {}
    for i, host in ((1, "orm01.krk.test"), (2, "orm02.krk.test")):
        s = make_state("full")
        s.pk, s.display_id = i, f"MAR_KRK_ORM_0{i}"
        s.berths = [_berth(b, f"A-{b:02d}", i, 0) for b in (1, 2, 3, 4)]
        s.service_email, s.service_password = "erp@krk.sim", "krk-sim-pass"
        s.contract = "r14"
        states[host], apps[host] = s, create_app(s)

    class ByHost(httpx.AsyncBaseTransport):
        def __init__(self):
            self.t = {h: httpx.ASGITransport(app=a) for h, a in apps.items()}

        async def handle_async_request(self, request):
            return await self.t[request.url.host].handle_async_request(request)

    async def _no_sleep(_s):
        return None

    factory = get_pedestal_factory()
    factory.transport, factory.sleep = ByHost(), _no_sleep

    with TestClient(erp_app) as client:
        tok = client.post("/api/auth/login", json={"email": "growth@check.erp",
                                                   "password": "growth-pass"}).json()
        h = {"Authorization": f"Bearer {tok['access_token']}"}
        mid = client.post("/api/marinas", headers=h, json={
            "name": "Krk", "pedestal_api_base_url": "http://orm01.krk.test",
            "pedestal_service_email": "erp@krk.sim",
            "pedestal_service_password": "krk-sim-pass"}).json()["id"]
        db = SessionLocal()
        cabs = {}
        try:
            for i, host in ((1, "orm01.krk.test"), (2, "orm02.krk.test")):
                c = svc.provision_cabinet(
                    db, marina_id=mid, pedestal_pk=i, display_id=f"MAR_KRK_ORM_0{i}",
                    device_type="full", base_url=f"http://{host}", service_email="erp@krk.sim",
                    service_password="krk-sim-pass", erp_api_key="sim-erp-key",
                    webhook_key=f"hook-{i}")
                for b in (1, 2, 3, 4):
                    berth = svc.create_berth(db, marina_id=mid, berth_number=f"{i}-{b:02d}",
                                             cabinet_id=c.id, cabinet_berth_id=b)
                    svc.set_berth_outlets(db, berth, [f"Q{b}"] + (["V1"] if b <= 2 else ["V2"]),
                                          assigned_by="growth@check")
                cabs[host] = (c.id, i)
            cust = Customer(marina_id=mid, external_ref="krk-guest", full_name="Gost")
            db.add(cust)
            db.commit()
            cust_id = cust.id
        finally:
            db.close()

        def snapshot() -> dict:
            out = {}
            with engine.connect() as conn:
                for t in sorted(inspect(engine).get_table_names()):
                    if t == "alembic_version":
                        continue
                    rows = conn.execute(text(f'SELECT count(*) FROM "{t}"')).scalar()  # noqa: S608 — names from the catalogue
                    size = None
                    if engine.dialect.name == "postgresql":
                        size = conn.execute(text("SELECT pg_total_relation_size(:t)"),
                                            {"t": t}).scalar()
                    out[t] = {"rows": rows, "bytes": size}
            if engine.dialect.name == "sqlite":
                out["_file_bytes"] = Path(db_url.replace("sqlite:///", "")).stat().st_size
            return out

        def outlet_id(cab_id, name):
            d = SessionLocal()
            try:
                return d.query(Outlet.id).filter_by(cabinet_id=cab_id, outlet_name=name).scalar()
            finally:
                d.close()

        before = snapshot()
        col = Collector()
        seq = {"sid": 1000, "alarm": 1, "ref": 0}
        open_sessions: dict = {}          # (host, outlet) -> (erp id, cabinet sid, started)
        t0 = time.monotonic()
        per_day = []

        for minute in range(args.days * 24 * 60):
            now = start + timedelta(minutes=minute)
            clock["now"] = now
            hh, mm = now.hour, now.minute
            for host, s in states.items():
                cab_id, pk = cabs[host]
                # sessions start / end
                for hour, outlet in SESSIONS_PER_DAY:
                    key = (host, outlet)
                    sock = s.sockets[int(outlet[1]) - 1]
                    if (hh, mm) == (hour, 0):
                        seq["sid"] += 1
                        seq["ref"] += 1
                        ref = f"erp-{seq['ref']}"
                        d = SessionLocal()
                        try:
                            es = ErpSession(erp_ref=ref, cabinet_id=cab_id,
                                            outlet_id=outlet_id(cab_id, outlet),
                                            customer_id=cust_id, session_type="electricity",
                                            status="active")
                            d.add(es)
                            d.commit()
                            open_sessions[key] = (es.id, seq["sid"], now, sock.energy_kwh, ref)
                        finally:
                            d.close()
                        s.nfc_sessions[seq["sid"]] = session_payload(
                            session_id=seq["sid"], cabinet_id=s.display_id, socket_id=outlet,
                            customer_id=None, erp_ref=ref, status="active",
                            activated_at=iso_z(now), duration_minutes=None, energy_kwh=None,
                            meter_energy_start_kwh=sock.energy_kwh, meter_energy_end_kwh=None,
                            consumption_source=None)
                        sock.current, sock.power_kw = 10.0, 2.3
                    if key in open_sessions and now - open_sessions[key][2] >= timedelta(
                            minutes=SESSION_MIN):
                        _, sid, started, e0, ref = open_sessions.pop(key)
                        sock.current, sock.power_kw = 0.0, 0.0
                        p = session_payload(
                            session_id=sid, cabinet_id=s.display_id, socket_id=outlet,
                            customer_id=None, erp_ref=ref, status="ended",
                            activated_at=iso_z(started), duration_minutes=float(SESSION_MIN),
                            energy_kwh=round(sock.energy_kwh - e0, 4),
                            meter_energy_start_kwh=e0, meter_energy_end_kwh=sock.energy_kwh,
                            consumption_source="register")
                        s.nfc_sessions[sid] = p
                        client.post(f"/api/webhooks/cabinet/{cab_id}",
                                    headers={"X-API-Key": f"hook-{pk}"},
                                    json={"event": "session_completed", "data": p,
                                          "timestamp": iso_z(now)})
                # standalone hour on cabinet 2 (D19)
                if pk == 2:
                    hour, outlet, length = STANDALONE
                    sock = s.sockets[int(outlet[1]) - 1]
                    if (hh, mm) == (hour, 0):
                        s.smart_mode = False
                        sock.current, sock.power_kw = 8.0, 1.8
                    if (hh, mm) == (hour + length // 60, length % 60):
                        s.smart_mode = True
                        sock.current, sock.power_kw = 0.0, 0.0
                # one alarm a day, at 10:00
                if (hh, mm) == (10, 0):
                    s.alarms = [{"id": seq["alarm"], "pedestal_id": pk, "status": "triggered",
                                 "alarm_type": "moisture"}]
                    seq["alarm"] += 1
                if (hh, mm) == (10, 30):
                    s.alarms = []
                # registers move with power
                for sock in s.sockets:
                    if sock.power_kw:
                        sock.energy_kwh = round(sock.energy_kwh + sock.power_kw / 60, 4)
            asyncio.run(col.tick())
            if (minute + 1) % 1440 == 0:
                per_day.append(snapshot())
                d = (minute + 1) // 1440
                print(f"  day {d}: {sum(v['rows'] for k, v in per_day[-1].items() if k != '_file_bytes')}"
                      f" rows, {time.monotonic() - t0:.0f} s", flush=True)

        after = per_day[-1]

        # ── the proof: jump past every window, run retention ──────────────────
        d = SessionLocal()
        try:
            kwh_before = d.query(func.sum(ConsumptionInterval.energy_kwh)).scalar() or 0
            sessions_before = d.query(func.count(ErpSession.id)).scalar()
            longest = max(settings.retention_command_audit_days, settings.retention_audit_log_days,
                          settings.retention_intervals_days, settings.retention_alarm_log_days)
            clock["now"] = start + timedelta(days=args.days + longest + 1)
            deleted = retention.run(d, clock["now"])
            kwh_monthly = d.query(func.sum(ConsumptionMonthly.energy_kwh)).scalar() or 0
            left = snapshot()
            sessions_after = d.query(func.count(ErpSession.id)).scalar()
        finally:
            d.close()
    erp_time._simulated_clock = None

    # ── report ────────────────────────────────────────────────────────────────
    windows = {name: days for name, (_, _, days) in retention.windows().items()}
    windows["consumption_intervals"] = settings.retention_intervals_days
    days = args.days
    lines, ceiling_bytes, problems = [], 0, []
    tables = [t for t in after if not t.startswith("_")]
    # the rate is measured from the end of day 1 when there is more than one day:
    # day 1 also holds one-off rows (one meter state per outlet, the first cache rows)
    base, span = (per_day[0], days - 1) if days > 1 else (before, days)
    for t in tables:
        r0, r1 = before[t]["rows"], after[t]["rows"]
        b1 = after[t]["bytes"]
        per = (r1 - base[t]["rows"]) / span
        win = windows.get(t)
        if win is not None:
            ceil_rows = per * win
            kind = f"{win} d"
        else:
            ceil_rows = r1 + per * 365          # kept for good: one year more of it
            kind = "kept (+1 y)"
        bpr = (b1 / r1) if (b1 and r1) else None
        ceil_b = ceil_rows * bpr if bpr else None
        if ceil_b:
            ceiling_bytes += ceil_b
        lines.append((t, r0, r1, per, kind, round(ceil_rows), b1, ceil_b))
        if win is not None and left[t]["rows"] != 0 and t != "pedestal_cache":
            problems.append(f"{t}: {left[t]['rows']} rows left after every window passed")
    if abs(Decimal(str(kwh_before)) - Decimal(str(kwh_monthly))) > Decimal("0.001"):
        problems.append(f"monthly aggregate {kwh_monthly} kWh != intervals {kwh_before} kWh")
    if sessions_after != sessions_before:
        problems.append(f"sessions {sessions_before} -> {sessions_after}: accounting was deleted")
    if engine.dialect.name == "sqlite":
        growth_b = after["_file_bytes"] - before["_file_bytes"]
        rows_growth = sum(after[t]["rows"] - before[t]["rows"] for t in tables)
        bpr = growth_b / rows_growth if rows_growth else 0
        ceiling_bytes = sum(row[5] for row in lines) * bpr
    ceiling_mb = ceiling_bytes / 1e6
    if ceiling_mb > BUDGET_MB:
        problems.append(f"projected {ceiling_mb:.0f} MB > budget {BUDGET_MB} MB")

    print(f"\nGROWTH ({engine.dialect.name}, 2 cabinets, {days} simulated days)")
    print(f"  {'table':<24}{'day 0':>8}{f'day {days}':>9}{'/day':>9}  {'window':<12}"
          f"{'ceiling rows':>13}{'bytes now':>12}")
    for t, r0, r1, per, kind, ceil_rows, b1, _ in lines:
        if r1 == 0 and r0 == 0:
            continue
        print(f"  {t:<24}{r0:>8}{r1:>9}{per:>9.1f}  {kind:<12}{ceil_rows:>13}"
              f"{(b1 if b1 is not None else '-'):>12}")
    if engine.dialect.name == "sqlite":
        print(f"  file: {before['_file_bytes']} B -> {after['_file_bytes']} B")
    print(f"  retention after every window: deleted {json.dumps(deleted)}")
    print(f"  intervals {float(kwh_before):.3f} kWh -> monthly {float(kwh_monthly):.3f} kWh; "
          f"sessions {sessions_before} -> {sessions_after}")
    print(f"  projected steady state: {ceiling_mb:.1f} MB (budget {BUDGET_MB} MB)")
    summary = {"dialect": engine.dialect.name, "days": days,
               "rows_day0": sum(before[t]["rows"] for t in tables),
               "rows_dayN": sum(after[t]["rows"] for t in tables),
               "ceiling_mb": round(ceiling_mb, 1), "problems": problems}
    print("GROWTH_JSON " + json.dumps(summary))
    for p in problems:
        print(f"  [FAIL] {p}")
    print(f"GROWTH: {'OK' if not problems else 'FAILED'}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
