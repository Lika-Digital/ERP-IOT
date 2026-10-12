"""One clock for the whole backend.

`datetime.utcnow()` is deprecated (Python 3.12) and returns a naive datetime
that merely happens to be UTC. Every DateTime column in this schema is naive
and stores UTC, so `utcnow()` keeps exactly that contract — naive UTC — while
getting the value from an aware clock. Switching columns to timezone-aware
(`timestamptz`) is a schema decision, not part of spec §11 O18.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current UTC time as a naive datetime, matching the naive-UTC columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
