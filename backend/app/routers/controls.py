"""Controls router — allow/deny/stop sessions with full audit logging."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.marina import Marina
from ..models.user import User
from ..services.pedestal_api_factory import PedestalAPIClientFactory, get_pedestal_factory
from ..services.audit_log import record_action
from .auth import get_current_user, require_marina_access

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marinas", tags=["controls"])


class DenyRequest(BaseModel):
    reason: Optional[str] = None


def _get_marina_and_check_access(
    marina_id: int, user: User, db: Session
) -> Marina:
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")
    require_marina_access(marina_id, user, db)
    return marina


@router.post("/{marina_id}/sessions/{session_id}/allow")
async def allow_session(
    marina_id: int,
    session_id: int,
    pedestal_id: Optional[int] = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """Allow a pending session on the Pedestal SW + log to audit trail."""
    marina = _get_marina_and_check_access(marina_id, user, db)

    client = factory.get_client(marina_id, db)
    result = await client.allow_session(session_id)

    record_action(
        db,
        user_id=user.id,
        marina_id=marina_id,
        action="allow_session",
        pedestal_id=pedestal_id,
        target_id=session_id,
        details={"result": result},
    )
    log.info(f"[CONTROLS] allow_session marina={marina_id} session={session_id} user={user.id}")
    return result


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
    """Deny a pending session with optional reason + log to audit trail."""
    marina = _get_marina_and_check_access(marina_id, user, db)

    client = factory.get_client(marina_id, db)
    result = await client.deny_session(session_id, body.reason)

    record_action(
        db,
        user_id=user.id,
        marina_id=marina_id,
        action="deny_session",
        pedestal_id=pedestal_id,
        target_id=session_id,
        details={"reason": body.reason, "result": result},
    )
    log.info(f"[CONTROLS] deny_session marina={marina_id} session={session_id} user={user.id}")
    return result


@router.post("/{marina_id}/sessions/{session_id}/stop")
async def stop_session(
    marina_id: int,
    session_id: int,
    pedestal_id: Optional[int] = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """Stop an active session + log to audit trail."""
    marina = _get_marina_and_check_access(marina_id, user, db)

    client = factory.get_client(marina_id, db)
    result = await client.stop_session(session_id)

    record_action(
        db,
        user_id=user.id,
        marina_id=marina_id,
        action="stop_session",
        pedestal_id=pedestal_id,
        target_id=session_id,
        details={"result": result},
    )
    log.info(f"[CONTROLS] stop_session marina={marina_id} session={session_id} user={user.id}")
    return result


@router.post("/{marina_id}/pedestals/{pedestal_id}/diagnostics")
async def run_diagnostics(
    marina_id: int,
    pedestal_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """Run diagnostics on a pedestal."""
    marina = _get_marina_and_check_access(marina_id, user, db)

    client = factory.get_client(marina_id, db)
    result = await client.run_diagnostics(pedestal_id)

    record_action(
        db,
        user_id=user.id,
        marina_id=marina_id,
        action="run_diagnostics",
        pedestal_id=pedestal_id,
        details={"result": result},
    )
    return result
