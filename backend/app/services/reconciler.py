"""Pull reconciliation of sessions, per cabinet (spec §5.2, D7, R14).

Two modes, chosen by asking the cabinet, not by configuration:

  range    R14 b — sessions by END time, [ended_from, ended_to), paged. Each run
           continues where the last good one stopped (with an overlap, because
           the cabinet may commit a session a little after its end time). Then
           R14 c: the ERP acknowledges, explicitly, the sessions whose final
           figure it stored.
  by_user  today's cabinet (a709cf8): the range route answers 404 "Not Found",
           so the ERP reads by-user — ONLY here, never for display (§7.2 R2,
           TC-ERP-SIM-00g) — for the customers with an open or not yet
           reconciled ERP session on this cabinet; the nightly pass widens that
           to every customer with a session in the last 30 days.

Every run is a row in reconciliation_runs: the ERP's own "last reconciled"
(§6.3), which it does not take from the cabinet's detector.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..cabinet.client import CabinetClient, is_missing_route
from ..models.billing import Customer
from ..models.cabinet import Cabinet
from ..models.metering import ErpSession, ReconciliationRun
from . import session_sync

log = logging.getLogger(__name__)

OVERLAP = timedelta(minutes=10)
FIRST_LOOKBACK = timedelta(days=2)
NIGHTLY_LOOKBACK = timedelta(days=30)
PAGE = 100


def _last_good_window_to(db: Session, cab: Cabinet):
    row = (db.query(ReconciliationRun)
           .filter(ReconciliationRun.cabinet_id == cab.id, ReconciliationRun.ok.is_(True),
                   ReconciliationRun.mode == "range")
           .order_by(ReconciliationRun.id.desc()).first())
    return row.window_to if row else None


def _count(run: ReconciliationRun, result: str) -> None:
    run.sessions_seen += 1
    if result == "updated":
        run.sessions_updated += 1
    elif result == "unknown":
        run.sessions_unknown += 1


async def reconcile(db: Session, cab: Cabinet, client: CabinetClient, now: datetime,
                    *, nightly: bool = False) -> ReconciliationRun:
    run = ReconciliationRun(cabinet_id=cab.id, mode="range", started_at=now, ok=False,
                            sessions_seen=0, sessions_updated=0, sessions_unknown=0,
                            sessions_acked=0)
    db.add(run)
    db.commit()
    try:
        if not client.has_channel_b:
            run.error = "no X-API-Key configured for this cabinet (channel B)"
        else:
            await _range(db, cab, client, run, now, nightly)
    except Exception as exc:  # noqa: BLE001 — a failed run is a row with the reason, not a crash
        db.rollback()
        log.exception("[reconcile] %s failed", cab.display_id)
        run.ok, run.error = False, f"{type(exc).__name__}: {exc}"[:2000]
    run.finished_at = now
    db.add(run)
    db.commit()
    return run


async def _range(db, cab, client, run, now, nightly) -> None:
    last = _last_good_window_to(db, cab)
    frm = now - NIGHTLY_LOOKBACK if nightly else (last - OVERLAP if last else now - FIRST_LOOKBACK)
    run.window_from, run.window_to = frm, now
    offset = 0
    while True:
        out = await client.nfc_sessions_ended_between(frm, now, limit=PAGE, offset=offset)
        if is_missing_route(out):
            run.mode, run.window_from, run.window_to = "by_user", None, None
            await _by_user(db, cab, client, run, now, nightly)
            return
        if not out.ok:
            run.error = f"{out.code}: {out.cabinet_detail or ''}"[:2000]
            return
        rows = (out.data or {}).get("sessions") or []
        for raw in rows:
            _count(run, session_sync.apply(db, cab, raw, final_by_pull=True, now=now))
        db.commit()
        total = (out.data or {}).get("total")
        offset += len(rows)
        if not rows or (total is not None and offset >= total):
            break
    await _refresh_active(db, cab, client, run, now)
    await _ack(db, cab, client, run, now)
    run.ok = True


async def _refresh_active(db, cab, client, run, now) -> None:
    """With R14 b the single-session read is read-only, so open ERP sessions the
    cabinet already knows are refreshed one by one (they have not ended yet, so the
    range does not contain them)."""
    open_ = (db.query(ErpSession)
             .filter(ErpSession.cabinet_id == cab.id, ErpSession.status == "active",
                     ErpSession.cabinet_session_id.isnot(None)).all())
    for s in open_:
        out = await client.nfc_session_for_reconciliation(s.cabinet_session_id)
        if out.ok and isinstance(out.data, dict):
            _count(run, session_sync.apply(db, cab, out.data, final_by_pull=True, now=now))
    db.commit()


async def _ack(db, cab, client, run, now) -> None:
    rows = (db.query(ErpSession)
            .filter(ErpSession.cabinet_id == cab.id, ErpSession.reconciled_at.isnot(None),
                    ErpSession.ack_sent_at.is_(None), ErpSession.cabinet_session_id.isnot(None))
            .all())
    if not rows:
        return
    out = await client.nfc_ack([s.cabinet_session_id for s in rows])
    if is_missing_route(out):
        return                      # the cabinet has no R14 c yet
    if out.ok:
        for s in rows:
            s.ack_sent_at = now
        run.sessions_acked = len(rows)
        db.commit()
    else:
        log.warning("[reconcile] %s: ack refused: %s %s", cab.display_id, out.code,
                    out.cabinet_detail)


async def _by_user(db, cab, client, run, now, nightly) -> None:
    q = (db.query(Customer.external_ref).join(ErpSession, ErpSession.customer_id == Customer.id)
         .filter(ErpSession.cabinet_id == cab.id, Customer.external_ref.isnot(None)))
    if nightly:
        q = q.filter(ErpSession.created_at >= now - NIGHTLY_LOOKBACK)
    else:
        q = q.filter(or_(ErpSession.status.in_(("reserved", "active")),
                         ErpSession.reconciled_at.is_(None)))
    refs = sorted({r for (r,) in q.distinct()})
    for ref in refs:
        out = await client.nfc_sessions_by_user_for_reconciliation(ref, limit=PAGE)
        if not out.ok:
            run.error = f"{out.code} for user {ref}: {out.cabinet_detail or ''}"[:2000]
            return
        for raw in (out.data or {}).get("sessions") or []:
            _count(run, session_sync.apply(db, cab, raw, final_by_pull=True, now=now))
        db.commit()
    run.ok = True
