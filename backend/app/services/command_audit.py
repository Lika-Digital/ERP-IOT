"""command_audit — EVERY control command, written BEFORE the call (spec §4.7, §5.3, D13).

`begin` commits a row with outcome NULL before anything is sent, `complete`
fills in the outcome. A command that never got an answer (the process died,
the request hung) stays visible as a row without an outcome — the point of
writing first.

An operator command without a reason is refused by the database (CHECK); the
router refuses it earlier with a 422, so it is never sent.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ..cabinet.outcomes import Outcome
from ..models.metering import CommandAudit
from ..utils.time import utcnow


def begin(db: Session, *, cabinet_id: int, endpoint_key: str, action: str, actor_type: str,
          actor_ref: Optional[str], reason: Optional[str], request_url: str,
          outlet_id: Optional[int] = None, tag_source: Optional[str] = None,
          source_ip: Optional[str] = None) -> CommandAudit:
    row = CommandAudit(cabinet_id=cabinet_id, outlet_id=outlet_id, endpoint_key=endpoint_key,
                       action=action, actor_type=actor_type, actor_ref=actor_ref,
                       tag_source=tag_source, reason=reason, request_url=request_url,
                       source_ip=source_ip)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def complete(db: Session, row: CommandAudit, outcome: Outcome) -> CommandAudit:
    row.outcome = outcome.code
    row.http_status = outcome.http_status
    row.detail = (outcome.cabinet_detail or None) and outcome.cabinet_detail[:1000]
    row.completed_at = utcnow()
    db.add(row)
    db.commit()
    return row
