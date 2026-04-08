"""Pydantic schemas for marina CRUD and health responses."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class MarinaCreate(BaseModel):
    name: str
    location: Optional[str] = None
    timezone: str = "UTC"
    logo_url: Optional[str] = None
    pedestal_api_base_url: str
    pedestal_service_email: str
    pedestal_service_password: str  # plaintext; router encrypts before storing
    webhook_secret: Optional[str] = None
    status: str = "active"


class MarinaUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    timezone: Optional[str] = None
    logo_url: Optional[str] = None
    pedestal_api_base_url: Optional[str] = None
    pedestal_service_email: Optional[str] = None
    # Supply only when changing the password; omit to keep existing
    pedestal_service_password: Optional[str] = None
    webhook_secret: Optional[str] = None
    status: Optional[str] = None


class MarinaResponse(BaseModel):
    id: int
    name: str
    location: Optional[str]
    timezone: str
    logo_url: Optional[str]
    pedestal_api_base_url: str
    pedestal_service_email: Optional[str]
    # Encrypted password is never returned to the client
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MarinaAccessGrant(BaseModel):
    user_id: int
    marina_id: int
