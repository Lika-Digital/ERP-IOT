"""Pydantic schemas for authentication endpoints."""
from pydantic import BaseModel, EmailStr
from typing import Optional, List


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    token: str


class UserMeResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    role: str
    marina_ids: List[int]
    is_active: bool

    model_config = {"from_attributes": True}
