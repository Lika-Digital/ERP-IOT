"""Retention — written in the same commit as the collector (D7, spec §4.7).

Every window is one number in app/config.py. What is not here is kept for good
on purpose: sessions, credit_ledger, billing_records (accounting), the monthly
consumption aggregate (tiny), outlet_meter_state and cabinet rows (one per
outlet / cabinet, updated in place), admin_imports (files an Admin chose to
import) and security_rule_settings (one row per rule).

consumption_intervals are not just deleted: rows older than the window are
first added into consumption_monthly, in the same transaction as their delete,
chunk by chunk — a crash between chunks neither loses nor double-counts.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models.berth import BerthReservation
from ..models.cache import AlarmLog, AuditLog, PedestalCache, SessionLog, SyncLog
from ..models.metering import (CommandAudit, ConsumptionInterval, ConsumptionMonthly,
                               ReconciliationRun)
from ..models.security import DecoyHit, SecurityAlarm, ServiceWindow
from ..models.user import AuthAudit, SetupToken
from ..utils.time import utcnow

log = logging.getLogger(__name__)

CHUNK = 5000


def windows() -> dict:
    """table -> (time column, days). The single source; the spec table quotes it."""
    s = settings
    return {
        "sync_log": (SyncLog, SyncLog.started_at, s.retention_sync_log_days),
        "session_log": (SessionLog, SessionLog.recorded_at, s.retention_session_log_days),
        "alarm_log": (AlarmLog, AlarmLog.received_at, s.retention_alarm_log_days),
        "command_audit": (CommandAudit, CommandAudit.created_at, s.retention_command_audit_days),
        "audit_log": (AuditLog, AuditLog.performed_at, s.retention_audit_log_days),
        "reconciliation_runs": (ReconciliationRun, ReconciliationRun.started_at,
                                s.retention_reconciliation_days),
        "pedestal_cache": (PedestalCache, PedestalCache.last_synced_at, s.retention_cache_days),
        # D20 (spec §4.9): sign-in evidence weighs like command_audit; a setup link
        # is useless once expired and kept a while only to explain "my link failed"
        "auth_audit": (AuthAudit, AuthAudit.created_at, s.retention_auth_audit_days),
        "setup_tokens": (SetupToken, SetupToken.expires_at, s.retention_setup_tokens_days),
        # D21 (spec §13.1): the agent's alarms and the decoys' touches are evidence;
        # a service window is only needed to explain the door signals around it
        "security_alarms": (SecurityAlarm, SecurityAlarm.created_at,
                            s.retention_security_alarms_days),
        "decoy_hits": (DecoyHit, DecoyHit.observed_at, s.retention_decoy_hits_days),
        "service_windows": (ServiceWindow, ServiceWindow.to_at, s.retention_service_windows_days),
        # D28: a reservation explains an occupancy figure for as long as a session does
        "berth_reservations": (BerthReservation, BerthReservation.ends_at,
                               s.retention_berth_reservations_days),
    }


def _delete_older(db: Session, model, col, cutoff: datetime) -> int:
    pk = model.__mapper__.primary_key[0]
    total = 0
    while True:
        ids = db.execute(select(pk).where(col < cutoff).limit(CHUNK)).scalars().all()
        if not ids:
            return total
        db.execute(delete(model).where(pk.in_(ids)))
        db.commit()
        total += len(ids)


def _month(dt: datetime) -> date:
    return date(dt.year, dt.month, 1)


def _roll_up_intervals(db: Session, cutoff: datetime) -> int:
    total = 0
    while True:
        rows = (db.query(ConsumptionInterval).filter(ConsumptionInterval.to_at < cutoff)
                .order_by(ConsumptionInterval.id).limit(CHUNK).all())
        if not rows:
            return total
        agg: dict = {}
        for r in rows:
            k = (r.outlet_id, _month(r.from_at), bool(r.standalone))
            e, w, n = agg.get(k, (None, None, 0))
            if r.energy_kwh is not None:
                e = (e or Decimal(0)) + Decimal(r.energy_kwh)
            if r.water_liters is not None:
                w = (w or Decimal(0)) + Decimal(r.water_liters)
            agg[k] = (e, w, n + 1)
        for (outlet_id, month, standalone), (e, w, n) in agg.items():
            m = (db.query(ConsumptionMonthly)
                 .filter_by(outlet_id=outlet_id, month=month, standalone=standalone).first())
            if m is None:
                m = ConsumptionMonthly(outlet_id=outlet_id, month=month, standalone=standalone,
                                       interval_count=0)
                db.add(m)
            if e is not None:
                m.energy_kwh = (Decimal(m.energy_kwh) if m.energy_kwh is not None
                                else Decimal(0)) + e
            if w is not None:
                m.water_liters = (Decimal(m.water_liters) if m.water_liters is not None
                                  else Decimal(0)) + w
            m.interval_count += n
        db.execute(delete(ConsumptionInterval)
                   .where(ConsumptionInterval.id.in_([r.id for r in rows])))
        db.commit()          # roll-up and delete of one chunk: one transaction
        total += len(rows)


def run(db: Session, now: datetime | None = None) -> dict:
    now = now or utcnow()
    out = {}
    for name, (model, col, days) in windows().items():
        out[name] = _delete_older(db, model, col, now - timedelta(days=days))
    out["consumption_intervals"] = _roll_up_intervals(
        db, now - timedelta(days=settings.retention_intervals_days))
    if any(out.values()):
        log.info("[retention] deleted %s", {k: v for k, v in out.items() if v})
    return out
