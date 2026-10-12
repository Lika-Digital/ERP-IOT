"""One clock for the whole backend — and the rule that every stored time is UTC.

Every DateTime column in this schema is naive and holds UTC (spec §4.0). Naive
UTC and naive local time look identical in the database, so the rule is held
in three places, not one:

  - `utcnow()` is the only clock; ruff's DTZ rules refuse `datetime.now()`
    without a zone, `utcnow()`, `today()` and friends in the source (O18);
  - `refuse_aware_datetimes` (registered in app/database.py) refuses an
    aware datetime at flush: on PostgreSQL a `timestamp without time zone`
    silently DROPS the offset, so 12:00+02:00 would be stored as 12:00;
  - tests/test_utc_storage.py runs the write paths in a process whose local
    zone is UTC+14 and fails if any stored time is local.

Cabinet times arrive as ISO strings with a trailing Z (its time_utils.iso_z);
`parse_utc` turns them into naive UTC.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


# Only scripts/growth_check.py sets this: it runs the real collector and retention
# through simulated days. Production and the app never touch it.
_simulated_clock = None


def utcnow() -> datetime:
    """Current UTC time as a naive datetime, matching the naive-UTC columns."""
    if _simulated_clock is not None:
        return _simulated_clock()
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(dt: datetime) -> datetime:
    """An aware datetime in any zone -> the same instant as naive UTC.

    A naive input is refused: it is either already UTC (then do not call this)
    or local (then it is a bug) — this function cannot tell which.
    """
    if dt.tzinfo is None:
        raise ValueError("to_naive_utc got a naive datetime; its zone is unknown")
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def parse_utc(value: Optional[str]) -> Optional[datetime]:
    """ISO-8601 from the cabinet -> naive UTC. 'Z' and offsets are honoured.

    A string without a zone is taken as UTC: the cabinet writes UTC everywhere
    and marks it with Z; older rows on the cabinet may lack the Z.
    """
    if value is None or value == "":
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt
    return to_naive_utc(dt)


class AwareDatetimeError(ValueError):
    """An aware datetime was about to be stored in a naive-UTC column."""


def refuse_aware_datetimes(session, flush_context, instances) -> None:
    """SQLAlchemy before_flush hook: no aware datetime reaches a DateTime column."""
    from sqlalchemy import DateTime
    from sqlalchemy import inspect as sa_inspect

    for obj in list(session.new) + list(session.dirty):
        mapper = sa_inspect(obj).mapper
        for col in mapper.columns:
            if not isinstance(col.type, DateTime):
                continue
            value = getattr(obj, mapper.get_property_by_column(col).key, None)
            if isinstance(value, datetime) and value.tzinfo is not None:
                raise AwareDatetimeError(
                    f"{type(obj).__name__}.{col.name} = {value.isoformat()} is aware; every "
                    f"stored time is naive UTC (spec §4.0) — convert with to_naive_utc()")
