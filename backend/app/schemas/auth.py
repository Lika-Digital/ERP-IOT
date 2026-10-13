"""Pydantic schemas for authentication and user endpoints (D20)."""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class MfaChallenge(BaseModel):
    """Answer to a correct password: a short token that opens ONLY the 2FA step."""
    mfa_token: str
    token_type: str = "mfa"
    mfa_enrolled: bool          # False -> the enrolment screen, True -> the code screen


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=40)


class EnrollStart(BaseModel):
    secret: str                 # for typing in by hand when the camera cannot read the QR
    otpauth_uri: str
    qr_svg: str


class EnrollDone(TokenResponse):
    backup_codes: List[str]     # shown ONCE


class BackupCodes(BaseModel):
    backup_codes: List[str]


class SetupCheck(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class SetupCheckResponse(BaseModel):
    email: str


class SetupRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str


class UserMeResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    role: str
    marina_ids: List[int]
    is_active: bool

    model_config = {"from_attributes": True}


# ── users (Admin) ─────────────────────────────────────────────────────────────

Role = Literal["admin", "marina_manager"]


class UserOut(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    marina_ids: List[int]
    password_set: bool
    mfa_enrolled: bool
    locked_until: Optional[datetime]
    last_login: Optional[datetime]
    created_at: datetime


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    full_name: Optional[str] = Field(default=None, max_length=200)
    role: Role
    marina_ids: List[int] = []


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=200)
    role: Optional[Role] = None
    is_active: Optional[bool] = None
    marina_ids: Optional[List[int]] = None


class SetupLink(BaseModel):
    link: str                   # shown ONCE; only its hash is stored
    expires_at: datetime


class UserCreated(BaseModel):
    user: UserOut
    setup: SetupLink


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class AuthAuditOut(BaseModel):
    id: int
    user_id: Optional[int]
    email_tried: Optional[str]
    event: str
    detail: Optional[str]
    actor_id: Optional[int]
    source_ip: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
