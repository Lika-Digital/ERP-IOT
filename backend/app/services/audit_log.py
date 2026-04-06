"""Audit log service — records every control action with user and marina context."""
import logging
from datetime import datetime
from typing import Optional, Any
from sqlalchemy.orm import Session

from ..models.cache import AuditLog

logger = logging.getLogger(__name__)


def record_action(
    db: Session,
    user_id: Optional[int],
    marina_id: int,
    action: str,
    pedestal_id: Optional[int] = None,
    target_id: Optional[int] = None,
    details: Optional[dict] = None,
) -> AuditLog:
    """
    Write one audit log entry.

    Args:
        db:           SQLAlchemy session (caller's transaction — committed here).
        user_id:      ID of the user performing the action (None = system).
        marina_id:    Marina this action belongs to.
        action:       Action name, e.g. 'allow_session', 'deny_session', 'stop_session',
                      'acknowledge_alarm'.
        pedestal_id:  Optional pedestal involved.
        target_id:    ID of the primary object acted upon (session_id, alarm_id, etc.).
        details:      Any extra context to store as JSON.

    Returns:
        The persisted AuditLog record.
    """
    entry = AuditLog(
        user_id=user_id,
        marina_id=marina_id,
        pedestal_id=pedestal_id,
        action=action,
        target_id=target_id,
        details=details,
        performed_at=datetime.utcnow(),
    )
    db.add(entry)
    try:
        db.commit()
        db.refresh(entry)
        logger.info(
            f"[AUDIT] user={user_id} marina={marina_id} action={action} "
            f"target={target_id} pedestal={pedestal_id}"
        )
    except Exception as exc:
        db.rollback()
        logger.error(f"Failed to write audit log: {exc}")
        raise
    return entry


def get_audit_log(
    db: Session,
    marina_id: int,
    limit: int = 200,
    action: Optional[str] = None,
    user_id: Optional[int] = None,
) -> list[AuditLog]:
    """Retrieve recent audit entries for a marina, newest first."""
    q = db.query(AuditLog).filter(AuditLog.marina_id == marina_id)
    if action:
        q = q.filter(AuditLog.action == action)
    if user_id is not None:
        q = q.filter(AuditLog.user_id == user_id)
    return q.order_by(AuditLog.performed_at.desc()).limit(limit).all()
