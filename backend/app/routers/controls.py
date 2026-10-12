"""Controls router — session allow/deny/stop, outlet commands, diagnostics.

Every command is audited WITH its outcome code, and answered through one
mapping (routers/_cabinet.py): a cabinet refusal is a 409/503 with a sentence,
never a 500 (spec §2.5). Before phase 2 this module had no try block at all and
a Smart Mode 409 from the cabinet surfaced as an ERP 500.
"""
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..cabinet.outcomes import Outcome
from ..database import get_db
from ..models.user import User
from ..services.audit_log import record_action
from ..services.pedestal_api_factory import PedestalAPIClientFactory, get_pedestal_factory
from ._cabinet import command, marina_client
from .auth import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marinas", tags=["controls"])


class DenyRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


class OutletCommand(BaseModel):
    action: Literal["activate", "stop"]


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


@router.post("/{marina_id}/sessions/{session_id}/allow")
async def allow_session(
    marina_id: int,
    session_id: int,
    pedestal_id: Optional[int] = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    _, client = marina_client(marina_id, user, db, factory)
    outcome = await client.allow_session(session_id, db=db)
    _audit(db, user, marina_id, "allow_session", outcome, pedestal_id, session_id)
    return command(outcome)


@router.post("/{marina_id}/sessions/{session_id}/deny")
async def deny_session(
    marina_id: int,
    session_id: int,
    body: DenyRequest = DenyRequest(),
    pedestal_id: Optional[int] = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    _, client = marina_client(marina_id, user, db, factory)
    outcome = await client.deny_session(session_id, body.reason, db=db)
    _audit(db, user, marina_id, "deny_session", outcome, pedestal_id, session_id,
           reason=body.reason)
    return command(outcome)


@router.post("/{marina_id}/sessions/{session_id}/stop")
async def stop_session(
    marina_id: int,
    session_id: int,
    pedestal_id: Optional[int] = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    _, client = marina_client(marina_id, user, db, factory)
    outcome = await client.stop_session(session_id, db=db)
    _audit(db, user, marina_id, "stop_session", outcome, pedestal_id, session_id)
    return command(outcome)


@router.post("/{marina_id}/pedestals/{pedestal_id}/outlets/{outlet}/cmd")
async def outlet_command(
    marina_id: int,
    pedestal_id: int,
    outlet: str,
    body: OutletCommand,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """Operator path (D3): switch an outlet by its real name, Q1-Q4 / V1-V2.

    `pedestal_id` here is the cabinet's numeric PK — the command routes refuse a
    display_id (NALAZ 3.1), and the contract module refuses to send one.
    """
    _, client = marina_client(marina_id, user, db, factory)
    outcome = await client.socket_cmd(pedestal_id, outlet, body.action, db=db)
    _audit(db, user, marina_id, f"outlet_{body.action}", outcome, pedestal_id,
           outlet=outlet)
    return command(outcome)


@router.post("/{marina_id}/pedestals/{pedestal_id}/diagnostics")
async def run_diagnostics(
    marina_id: int,
    pedestal_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    _, client = marina_client(marina_id, user, db, factory)
    outcome = await client.run_diagnostics(pedestal_id, db=db)
    _audit(db, user, marina_id, "run_diagnostics", outcome, pedestal_id)
    return command(outcome)
