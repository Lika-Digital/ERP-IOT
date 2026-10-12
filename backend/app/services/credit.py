"""Credit ledger — append-only; the balance is the newest row's balance_after (§4.5, D9).

The database refuses UPDATE and DELETE (trigger). This module is the only
writer, and it computes balance_after from the newest row inside the same
transaction, so every row can be checked on its own: previous + delta = after.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ..models.billing import CreditLedger
from .cabinets import DomainError

REASONS = ("topup", "consumption", "adjustment", "refund")


def balance(db: Session, customer_id: int) -> Decimal:
    last = (db.query(CreditLedger).filter(CreditLedger.customer_id == customer_id)
            .order_by(CreditLedger.id.desc()).first())
    return Decimal(str(last.balance_after)) if last else Decimal("0.00")


def post(db: Session, *, customer_id: int, delta, reason: str, created_by: Optional[str],
         session_id: Optional[int] = None) -> CreditLedger:
    if created_by is None or not str(created_by).strip():
        raise DomainError("created_by is required (§4.5) — top-ups are entered at reception")
    if reason not in REASONS:
        raise DomainError(f"reason must be one of {REASONS}")
    d = Decimal(str(delta)).quantize(Decimal("0.01"))
    if d == 0:
        raise DomainError("a zero row records nothing")
    if reason == "topup" and d < 0:
        raise DomainError("a top-up is positive; use 'adjustment' or 'refund'")
    q = db.query(CreditLedger).filter(CreditLedger.customer_id == customer_id)
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        q = q.with_for_update()   # two posts for one customer must not read the same "last"
    last = q.order_by(CreditLedger.id.desc()).first()
    prev = Decimal(str(last.balance_after)) if last else Decimal("0.00")
    row = CreditLedger(customer_id=customer_id, delta=d, reason=reason, session_id=session_id,
                       balance_after=prev + d, created_by=str(created_by).strip())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
