"""Schemas for the Security screen (spec §6.5, §13.1, D21)."""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from ..utils.time import to_naive_utc


def _utc(v: datetime) -> datetime:
    """A time from the browser carries its zone; it is stored as naive UTC (§4.0)."""
    if v.tzinfo is None:
        raise ValueError("a time must carry its zone (e.g. 2026-10-14T08:00:00Z)")
    return to_naive_utc(v)


class SecurityAlarmOut(BaseModel):
    id: int
    rule_id: str
    severity: str
    title: str
    why: str
    evidence: Any
    window_from: Optional[datetime]
    window_to: Optional[datetime]
    created_at: datetime
    state: str
    decided_by: Optional[int]
    decided_at: Optional[datetime]
    decision_note: Optional[str]


class AlarmDecision(BaseModel):
    state: Literal["acknowledged", "closed"]
    note: str = Field(min_length=1, max_length=2000)


class RuleOut(BaseModel):
    rule_id: str
    severity: str
    describe: str
    mode: Literal["shadow", "active"]
    decided_by: Optional[int]
    decided_at: Optional[datetime]


class RuleMode(BaseModel):
    mode: Literal["shadow", "active"]


class ServiceWindowIn(BaseModel):
    cabinet_id: int
    from_at: datetime
    to_at: datetime
    announced_by: str = Field(min_length=1, max_length=320)
    note: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("from_at", "to_at")
    @classmethod
    def _zone(cls, v: datetime) -> datetime:
        return _utc(v)


class ServiceWindowOut(BaseModel):
    id: int
    cabinet_id: int
    display_id: str
    from_at: datetime
    to_at: datetime
    announced_by: str
    note: Optional[str]
    created_by: Optional[int]
    created_at: datetime


class AdminImportIn(BaseModel):
    kind: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    filename: str = Field(min_length=1, max_length=255)
    content: Any


class AdminImportOut(BaseModel):
    id: int
    kind: str
    filename: str
    sha256: str
    imported_by: Optional[int]
    imported_at: datetime
