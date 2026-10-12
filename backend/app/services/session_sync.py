"""One cabinet session payload -> the ERP's session row. ONE path for pull and webhook.

The webhook is for speed, the pull is for money (D7). Both call `apply`, and
the only difference is `final_by_pull`: only the reconciler sets
`reconciled_at`, and the database refuses to bill a session without it.

Which ERP session a payload belongs to, in this order:
  1. erp_ref        — R14 b: the cabinet echoes the reference the ERP sent in /scan;
  2. (cabinet, cabinet_session_id) — once linked, the cabinet's id is enough;
  3. today's contract (a709cf8, no erp_ref): the customer's external_ref + the
     outlet, on an ERP session of this cabinet still waiting for the cabinet.
A payload that matches none is NOT the ERP's session and is not imported: the
cabinet ran it on its own, e.g. in Smart Mode OFF (D19).

A session already billed is never touched again.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ..cabinet.session_payload import CONSUMPTION_SOURCES, PayloadError, parse_session
from ..models.billing import Customer
from ..models.cabinet import Cabinet, Outlet
from ..models.metering import ErpSession
from ..utils.time import parse_utc

log = logging.getLogger(__name__)

RECOMPUTE_FINDINGS = {"recompute_mismatch", "recompute_impossible"}


def _dec(v: Optional[float], places: str) -> Optional[Decimal]:
    return None if v is None else Decimal(str(v)).quantize(Decimal(places))


def find(db: Session, cab: Cabinet, ps) -> Optional[ErpSession]:
    q = db.query(ErpSession).filter(ErpSession.cabinet_id == cab.id)
    if ps.erp_ref:
        s = q.filter(ErpSession.erp_ref == ps.erp_ref).first()
        if s is not None:
            return s
    s = q.filter(ErpSession.cabinet_session_id == ps.cabinet_session_id).first()
    if s is not None:
        return s
    if ps.customer_id and ps.outlet_name:
        return (q.join(Customer, Customer.id == ErpSession.customer_id)
                .join(Outlet, Outlet.id == ErpSession.outlet_id)
                .filter(Customer.external_ref == ps.customer_id,
                        Outlet.outlet_name == ps.outlet_name,
                        ErpSession.cabinet_session_id.is_(None),
                        ErpSession.status.in_(("reserved", "active")))
                .order_by(ErpSession.id.desc()).first())
    return None


def apply(db: Session, cab: Cabinet, raw: dict, *, final_by_pull: bool,
          now: datetime) -> str:
    """'updated' | 'unknown' (not the ERP's) | 'billed' (left alone) | 'invalid'.

    Does not commit: the caller decides the transaction.
    """
    try:
        ps = parse_session(raw)
    except PayloadError as exc:
        log.error("[sessions] cabinet %s sent a payload that breaks the contract: %s",
                  cab.display_id, exc)
        return "invalid"
    if ps.cabinet_display_id and ps.cabinet_display_id != cab.display_id:
        return "unknown"            # another cabinet on the same server
    s = find(db, cab, ps)
    if s is None:
        return "unknown"
    if s.billing_state == "billed":
        return "billed"

    review = ps.manual_review
    outlet = db.get(Outlet, s.outlet_id)
    if ps.outlet_name and outlet.outlet_name != ps.outlet_name:
        # the cabinet says another outlet: never move consumption silently (D10)
        log.error("[sessions] %s: ERP session %s is on %s, the cabinet says %s",
                  cab.display_id, s.erp_ref, outlet.outlet_name, ps.outlet_name)
        review = True
    if ps.session_type != s.session_type:
        log.error("[sessions] %s: ERP session %s is %s, the cabinet says %s",
                  cab.display_id, s.erp_ref, s.session_type, ps.session_type)
        review = True

    s.cabinet_session_id = ps.cabinet_session_id
    s.status = "ended" if ps.status == "ended" else "active"
    s.activated_at = parse_utc(ps.activated_at)
    s.duration_min = _dec(ps.duration_minutes, "0.01")
    if s.status == "ended" and s.activated_at is not None and ps.duration_minutes is not None:
        s.ended_at = s.activated_at + timedelta(minutes=float(ps.duration_minutes))
    if ps.session_type == "electricity":
        s.energy_kwh = _dec(ps.consumption, "0.0001")
        s.meter_e_start, s.meter_e_end = (_dec(ps.meter_start, "0.0001"),
                                          _dec(ps.meter_end, "0.0001"))
    else:
        s.water_liters = _dec(ps.consumption, "0.001")
        s.meter_w_start, s.meter_w_end = (_dec(ps.meter_start, "0.001"),
                                          _dec(ps.meter_end, "0.001"))
    if ps.consumption_source in CONSUMPTION_SOURCES:
        s.consumption_source = ps.consumption_source
    else:
        s.consumption_source = None     # the CHECK knows three words; anything else is review
        review = review or ps.consumption_source is not None
    s.recompute_ok = (None if ps.consumption is None else
                      not any(f.code in RECOMPUTE_FINDINGS for f in ps.findings))
    if review:
        s.billing_state = "manual_review"   # sticky: a person clears it, not the next poll
    if final_by_pull and s.status == "ended":
        s.reconciled_at = now
    return "updated"
