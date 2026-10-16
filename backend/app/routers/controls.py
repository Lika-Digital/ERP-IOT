"""Controls router — session allow/deny/stop, outlet commands, diagnostics.

Every command is answered through one mapping (routers/_cabinet.py): a cabinet
refusal is a 409/503 with a sentence, never a 500 (spec §2.5).

Phase 4 (spec §4.7, §5.3, D13): every command is written to command_audit
BEFORE it is sent and completed with its outcome, so a command that never got
an answer stays visible. That needs two things the request must carry:
  - the cabinet it goes to — a marina with no cabinet in the ERP gets no
    command (there is nothing to write the row against);
  - a REASON — an operator's command without one is refused here with 422 and
    by the database's CHECK; nothing is sent.
The older audit_log row is still written, with the outcome, as before.

P4 (spec §6.13): a command names its cabinet by the ERP's id (`cabinet`), because the
cabinets of one marina can share a pedestal pk; and in the demo marina nothing is ever
sent to a real cabinet — refused before the call, written to command_audit.
"""
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..cabinet.client import CabinetClient
from ..cabinet.outcomes import Outcome
from ..database import get_db
from ..models.berth import OutletNfcTag
from ..models.cabinet import Cabinet, Outlet
from ..models.marina import Marina
from ..models.user import User
from ..services import command_audit
from ..services.audit_log import record_action
from ..services.pedestal_api_factory import PedestalAPIClientFactory, get_pedestal_factory
from ._cabinet import (cabinet_entry, cabinet_of, command, is_demo_marina, marina_client,
                       refuse_real_cabinet_in_demo)
from .auth import get_current_user, require_marina_access

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marinas", tags=["controls"])

Reason = Field(min_length=3, max_length=500,
               description="Why — required for every operator command (§5.3)")


class CommandBody(BaseModel):
    reason: str = Reason


class DenyRequest(BaseModel):
    reason: str = Reason


class OutletCommand(BaseModel):
    action: Literal["activate", "stop"]
    reason: str = Reason


def _audit(db, user, marina_id, action, outcome: Outcome, pedestal_id=None, target_id=None,
           **extra) -> None:
    record_action(
        db, user_id=user.id, marina_id=marina_id, action=action, pedestal_id=pedestal_id,
        target_id=target_id,
        details={"outcome": outcome.code, "cabinet_status": outcome.http_status,
                 "result": outcome.data if outcome.ok else None, **extra},
    )
    log.info("[CONTROLS] %s marina=%s target=%s user=%s outcome=%s",
             action, marina_id, target_id, user.id, outcome.code)


def _cabinet_for(db: Session, marina_id: int, pedestal_pk: Optional[int]) -> Cabinet:
    q = db.query(Cabinet).filter(Cabinet.marina_id == marina_id)
    if pedestal_pk is not None:
        cab = q.filter(Cabinet.pedestal_pk == pedestal_pk).first()
    else:
        cabs = q.order_by(Cabinet.id).all()
        if len(cabs) > 1:
            raise HTTPException(status_code=422, detail={
                "code": "pedestal_required",
                "sentence": "The marina has more than one cabinet — the command must say which (pedestal_id)."})
        cab = cabs[0] if cabs else None
    if cab is None:
        raise HTTPException(status_code=409, detail={
            "code": "cabinet_not_configured",
            "sentence": "The cabinet is not configured in the ERP. No command is sent without a "
                        "command_audit record.",
            "endpoint": None, "is_stale": False, "data_as_of": None})
    return cab


def _target(marina_id: int, pedestal_pk: Optional[int], user: User, db: Session,
            factory: PedestalAPIClientFactory,
            cabinet_id: Optional[int] = None) -> tuple[Cabinet, CabinetClient]:
    marina_client(marina_id, user, db, factory, cabinet_id)   # 404 / access check
    if cabinet_id is not None:
        cab = cabinet_of(db, marina_id, cabinet_id)
        if pedestal_pk is not None and pedestal_pk != cab.pedestal_pk:
            raise HTTPException(status_code=422, detail={
                "code": "pedestal_mismatch",
                "sentence": f"Pedestal {pedestal_pk} is not cabinet {cab.display_id}."})
    else:
        cab = _cabinet_for(db, marina_id, pedestal_pk)
    return cab, factory.for_cabinet(cab)


async def _send(db, request: Request, user: User, cab: Cabinet, client: CabinetClient, *,
                endpoint_key: str, path_params: dict, action: str, reason: str, call,
                outlet_id: Optional[int] = None, tag_source: Optional[str] = None) -> Outcome:
    source_ip = request.client.host if request.client else None
    refuse_real_cabinet_in_demo(
        db, cab, endpoint_key=endpoint_key, action=action, actor_ref=user.email, reason=reason,
        request_url=client.url_for(endpoint_key, **path_params), source_ip=source_ip,
        outlet_id=outlet_id)
    row = command_audit.begin(
        db, cabinet_id=cab.id, outlet_id=outlet_id, endpoint_key=endpoint_key, action=action,
        actor_type="operator", actor_ref=user.email, reason=reason, tag_source=tag_source,
        request_url=client.url_for(endpoint_key, **path_params),
        source_ip=source_ip)
    outcome = await call()
    command_audit.complete(db, row, outcome)
    return outcome


@router.get("/{marina_id}/control/cabinets")
def control_cabinets(
    marina_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pedestal control's list (P4): the marina's cabinets as the ERP records them, each
    with whether it can be commanded and, when not, one sentence why. No cabinet is called."""
    if db.get(Marina, marina_id) is None:
        raise HTTPException(status_code=404, detail="Marina not found")
    require_marina_access(marina_id, user, db)
    demo = is_demo_marina(db, marina_id)
    cabs = db.query(Cabinet).filter(Cabinet.marina_id == marina_id).order_by(Cabinet.id).all()
    return {"marina_id": marina_id, "demo": demo,
            "cabinets": [cabinet_entry(c, demo=demo) for c in cabs]}


@router.post("/{marina_id}/sessions/{session_id}/allow")
async def allow_session(
    marina_id: int,
    session_id: int,
    body: CommandBody,
    request: Request,
    pedestal_id: Optional[int] = Query(default=None),
    cabinet: Optional[int] = Query(default=None, description="the ERP's cabinets.id (P4)"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    cab, client = _target(marina_id, pedestal_id, user, db, factory, cabinet)
    outcome = await _send(db, request, user, cab, client, endpoint_key="controls.allow",
                          path_params={"session_id": session_id}, action="allow",
                          reason=body.reason,
                          call=lambda: client.allow_session(session_id, db=db))
    _audit(db, user, marina_id, "allow_session", outcome, pedestal_id, session_id,
           reason=body.reason)
    return command(outcome)


@router.post("/{marina_id}/sessions/{session_id}/deny")
async def deny_session(
    marina_id: int,
    session_id: int,
    body: DenyRequest,
    request: Request,
    pedestal_id: Optional[int] = Query(default=None),
    cabinet: Optional[int] = Query(default=None, description="the ERP's cabinets.id (P4)"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    cab, client = _target(marina_id, pedestal_id, user, db, factory, cabinet)
    outcome = await _send(db, request, user, cab, client, endpoint_key="controls.deny",
                          path_params={"session_id": session_id}, action="deny",
                          reason=body.reason,
                          call=lambda: client.deny_session(session_id, body.reason, db=db))
    _audit(db, user, marina_id, "deny_session", outcome, pedestal_id, session_id,
           reason=body.reason)
    return command(outcome)


@router.post("/{marina_id}/sessions/{session_id}/stop")
async def stop_session(
    marina_id: int,
    session_id: int,
    body: CommandBody,
    request: Request,
    pedestal_id: Optional[int] = Query(default=None),
    cabinet: Optional[int] = Query(default=None, description="the ERP's cabinets.id (P4)"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    cab, client = _target(marina_id, pedestal_id, user, db, factory, cabinet)
    outcome = await _send(db, request, user, cab, client, endpoint_key="controls.stop",
                          path_params={"session_id": session_id}, action="stop",
                          reason=body.reason,
                          call=lambda: client.stop_session(session_id, db=db))
    _audit(db, user, marina_id, "stop_session", outcome, pedestal_id, session_id,
           reason=body.reason)
    return command(outcome)


@router.post("/{marina_id}/pedestals/{pedestal_id}/outlets/{outlet}/cmd")
async def outlet_command(
    marina_id: int,
    pedestal_id: int,
    outlet: str,
    body: OutletCommand,
    request: Request,
    cabinet: Optional[int] = Query(default=None, description="the ERP's cabinets.id (P4)"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """Operator path (D3): switch an outlet by its real name, Q1-Q4 / V1-V2.

    `pedestal_id` here is the cabinet's numeric PK — the command routes refuse a
    display_id (NALAZ 3.1), and the contract module refuses to send one. On
    activate, the ERP sends the outlet's tag FROM ITS OWN MAPPING and the audit
    says so (tag_source='mapping', never 'scan' — §5.3).
    """
    cab, client = _target(marina_id, pedestal_id, user, db, factory, cabinet)
    out_row = (db.query(Outlet).filter(Outlet.cabinet_id == cab.id,
                                       Outlet.outlet_name == outlet).first())
    tag = None
    if out_row is not None and body.action == "activate":
        t = (db.query(OutletNfcTag).filter(OutletNfcTag.outlet_id == out_row.id,
                                           OutletNfcTag.active.is_(True)).first())
        tag = t.uid_primary if t else None
    water = outlet.startswith("V")
    key = "controls.water_cmd" if water else "controls.socket_cmd"
    name = "valve_name" if water else "socket_name"
    outcome = await _send(
        db, request, user, cab, client, endpoint_key=key,
        path_params={"pedestal_id": pedestal_id, name: outlet}, action=body.action,
        reason=body.reason, outlet_id=out_row.id if out_row else None,
        tag_source="mapping" if tag else None,
        call=lambda: client.socket_cmd(pedestal_id, outlet, body.action, nfc_tag_id=tag, db=db))
    _audit(db, user, marina_id, f"outlet_{body.action}", outcome, pedestal_id,
           outlet=outlet, reason=body.reason)
    return command(outcome)


@router.post("/{marina_id}/pedestals/{pedestal_id}/diagnostics")
async def run_diagnostics(
    marina_id: int,
    pedestal_id: int,
    body: CommandBody,
    request: Request,
    cabinet: Optional[int] = Query(default=None, description="the ERP's cabinets.id (P4)"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    cab, client = _target(marina_id, pedestal_id, user, db, factory, cabinet)
    outcome = await _send(db, request, user, cab, client, endpoint_key="diagnostics.run",
                          path_params={"pedestal_id": pedestal_id}, action="run",
                          reason=body.reason,
                          call=lambda: client.run_diagnostics(pedestal_id, db=db))
    _audit(db, user, marina_id, "run_diagnostics", outcome, pedestal_id, reason=body.reason)
    return command(outcome)
