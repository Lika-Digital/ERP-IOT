"""Alarms router — list, acknowledge, and log alarms."""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.marina import Marina
from ..models.cache import AlarmLog
from ..models.user import User
from ..services.pedestal_api_factory import PedestalAPIClientFactory, get_pedestal_factory
from ..services.audit_log import record_action
from .auth import get_current_user, require_marina_access

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marinas", tags=["alarms"])


class AlarmAcknowledgeRequest(BaseModel):
    alarm_id: int
    pedestal_id: Optional[int] = None


@router.get("/{marina_id}/alarms/active")
async def get_active_alarms(
    marina_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """Fetch active (unacknowledged) alarms from Pedestal SW."""
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")
    require_marina_access(marina_id, user, db)

    client = factory.get_client(marina_id, db)
    data, is_stale = await client.get_active_alarms(marina_id, db)
    return {"marina_id": marina_id, "is_stale": is_stale, "alarms": data}


@router.get("/{marina_id}/alarms/log")
def get_alarm_log(
    marina_id: int,
    limit: int = Query(default=100, le=500),
    pedestal_id: Optional[int] = Query(default=None),
    unacknowledged_only: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return locally stored alarm log entries for a marina."""
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")
    require_marina_access(marina_id, user, db)

    q = db.query(AlarmLog).filter(AlarmLog.marina_id == marina_id)
    if pedestal_id is not None:
        q = q.filter(AlarmLog.pedestal_id == pedestal_id)
    if unacknowledged_only:
        q = q.filter(AlarmLog.acknowledged_at.is_(None))
    entries = q.order_by(AlarmLog.received_at.desc()).limit(limit).all()

    return {
        "marina_id": marina_id,
        "alarms": [
            {
                "id": e.id,
                "marina_id": e.marina_id,
                "pedestal_id": e.pedestal_id,
                "alarm_data": e.alarm_data,
                "received_at": e.received_at.isoformat(),
                "acknowledged_at": e.acknowledged_at.isoformat() if e.acknowledged_at else None,
                "acknowledged_by": e.acknowledged_by,
            }
            for e in entries
        ],
    }


@router.post("/{marina_id}/alarms/{alarm_id}/acknowledge")
async def acknowledge_alarm(
    marina_id: int,
    alarm_id: int,
    pedestal_id: Optional[int] = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """
    Acknowledge an alarm:
    1. Forward acknowledge to Pedestal SW
    2. Update local alarm_log record
    3. Write audit log entry
    """
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")
    require_marina_access(marina_id, user, db)

    client = factory.get_client(marina_id, db)
    try:
        result = await client.acknowledge_alarm(alarm_id)
    except Exception as exc:
        log.warning(f"[ALARMS] Pedestal SW acknowledge failed: {exc} — updating local log only")
        result = {"warning": "Pedestal SW unreachable; local log updated"}

    local_entry = (
        db.query(AlarmLog)
        .filter(AlarmLog.marina_id == marina_id)
        .filter(AlarmLog.alarm_data["id"].as_integer() == alarm_id)
        .first()
    )
    now = datetime.utcnow()
    if local_entry:
        local_entry.acknowledged_at = now
        local_entry.acknowledged_by = user.id
        db.commit()

    record_action(
        db,
        user_id=user.id,
        marina_id=marina_id,
        action="acknowledge_alarm",
        pedestal_id=pedestal_id,
        target_id=alarm_id,
        details={"result": result},
    )

    log.info(f"[ALARMS] acknowledge_alarm marina={marina_id} alarm={alarm_id} user={user.id}")
    return {"acknowledged": True, "alarm_id": alarm_id, "acknowledged_by": user.id, "result": result}
