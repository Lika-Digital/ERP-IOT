"""Router side of the cabinet contract: get a client, turn an Outcome into a response.

One mapping from outcome code to ERP HTTP status, so no router invents its own
and no cabinet outcome ever becomes a 500 (spec §2.5, TC-ERP-SIM-06/07).
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..cabinet import berth_status as bs
from ..cabinet.client import CabinetClient
from ..cabinet.outcomes import Outcome
from ..models.cabinet import Cabinet
from ..models.marina import Marina
from ..services import command_audit
from ..utils.time import utcnow
from ..models.user import User
from ..services.pedestal_api_factory import PedestalAPIClientFactory
from .auth import require_marina_access

# Commands: what the operator did was refused or could not be delivered.
COMMAND_HTTP = {
    "ok": 200,
    "already_ended": 200,          # staff closed it first; not an error (D10)
    "standalone": 409,
    "awaiting_plug": 409,
    "outlet_busy": 409,
    "nfc_mapping_mismatch": 409,
    "session_state_changed": 409,
    "conflict": 409,
    "not_found": 404,
    "not_enabled": 503,
    "capability_unavailable": 503,
    "no_contact": 503,
    "stale": 503,
    "cabinet_auth_failed": 503,
    "erp_bug": 502,                # our request was wrong; logged as a bug by the client
}


def marina_client(marina_id: int, user: User, db: Session,
                  factory: PedestalAPIClientFactory,
                  cabinet_id: Optional[int] = None) -> tuple[Marina, CabinetClient]:
    """The marina's client; with `cabinet_id` (the ERP's cabinets.id) THAT cabinet's own
    client, never the marina's first one (spec §6.13 P4)."""
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")
    require_marina_access(marina_id, user, db)
    if cabinet_id is not None:
        return marina, factory.for_cabinet(cabinet_of(db, marina_id, cabinet_id))
    try:
        return marina, factory.get_client(marina_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "cabinet_not_configured",
            "sentence": "This marina's cabinet is not configured.",
            "endpoint": None, "is_stale": False, "data_as_of": None,
            "reason": str(exc),
        }) from exc


def read(outcome: Outcome, field: str, **extra) -> dict:
    """A read always answers 200: data (possibly stale or None) + the outcome."""
    return {field: outcome.data if outcome.has_data else None,
            "is_stale": outcome.is_stale, "outcome": outcome.public(), **extra}


def command(outcome: Outcome) -> dict:
    status = COMMAND_HTTP[outcome.code]
    if status != 200:
        raise HTTPException(status_code=status, detail=outcome.public())
    return {"ok": True, "outcome": outcome.public(), "result": outcome.data}


# ─── Which cabinet, and may it be commanded (spec §6.13, P4) ─────────────────

DEMO_REAL_SENTENCE = ("This is a real cabinet in the demo marina. No command is sent to it "
                      "from here.")


def cabinet_of(db: Session, marina_id: int, cabinet_id: int) -> Cabinet:
    cab = db.get(Cabinet, cabinet_id)
    if cab is None or cab.marina_id != marina_id:
        raise HTTPException(status_code=404, detail="Cabinet not found in this marina")
    return cab


def is_demo_marina(db: Session, marina_id: int) -> bool:
    """A demo marina is a marina with at least one simulated cabinet (P4)."""
    return db.query(Cabinet.id).filter(Cabinet.marina_id == marina_id,
                                       Cabinet.is_simulated.is_(True)).first() is not None


def cabinet_entry(cab: Cabinet, *, demo: bool, now=None) -> dict:
    """The cabinet as the ERP records it — its display_id, SIM or real, connection (O51) —
    never the name the cabinet sends. Commands only when Online and Smart Mode ON, and
    never to a real cabinet of the demo marina."""
    connection = bs.connection_signal(bs.BerthSignals(
        now=now or utcnow(), last_heartbeat=cab.last_heartbeat_at, smart_mode=cab.smart_mode))
    if demo and not cab.is_simulated:
        sentence = DEMO_REAL_SENTENCE
    elif connection != "ONLINE":
        sentence = ("The cabinet has not been heard recently. No commands until it is back."
                    if connection == "STALE" else
                    "The cabinet is offline. No commands until it is back.")
    elif cab.smart_mode is not True:
        sentence = ("Smart Mode is off on this cabinet: it runs on its own and takes no "
                    "commands." if cab.smart_mode is False else
                    "Smart Mode has not been read from this cabinet yet. No commands until it is.")
    else:
        sentence = None
    return {"id": cab.id, "display_id": cab.display_id, "simulated": bool(cab.is_simulated),
            "connection": connection, "smart_mode": cab.smart_mode,
            "controllable": sentence is None, "sentence": sentence,
            "last_heartbeat_at": cab.last_heartbeat_at.isoformat() + "Z"
            if cab.last_heartbeat_at else None}


def refuse_real_cabinet_in_demo(db: Session, cab: Cabinet, *, endpoint_key: str, action: str,
                                actor_ref: str, reason: str, request_url: str,
                                source_ip: Optional[str] = None,
                                outlet_id: Optional[int] = None) -> None:
    """Rule (3) of §6.13, on the server: in the demo marina no command goes to a real
    cabinet. The refusal is written to command_audit and NOTHING is sent."""
    if cab.is_simulated or not is_demo_marina(db, cab.marina_id):
        return
    row = command_audit.begin(
        db, cabinet_id=cab.id, outlet_id=outlet_id, endpoint_key=endpoint_key, action=action,
        actor_type="operator", actor_ref=actor_ref, reason=reason, request_url=request_url,
        source_ip=source_ip)
    row.outcome = "demo_marina_real_cabinet"
    row.http_status = 409
    row.detail = "refused by the ERP before sending: real cabinet in the demo marina"
    row.completed_at = utcnow()
    db.commit()
    raise HTTPException(status_code=409, detail={
        "code": "demo_marina_real_cabinet", "sentence": DEMO_REAL_SENTENCE,
        "endpoint": endpoint_key, "is_stale": False, "data_as_of": None})
