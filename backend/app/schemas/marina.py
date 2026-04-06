"""Pydantic schemas for marina CRUD and health responses."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, HttpUrl


class MarinaCreate(BaseModel):
    name: str
    location: Optional[str] = None
    timezone: str = "UTC"
    logo_url: Optional[str] = None
    pedestal_api_base_url: str
    pedestal_api_key: str
    webhook_secret: Optional[str] = None
    status: str = "active"


class MarinaUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    timezone: Optional[str] = None
    logo_url: Optional[str] = None
    pedestal_api_base_url: Optional[str] = None
    pedestal_api_key: Optional[str] = None
    webhook_secret: Optional[str] = None
    status: Optional[str] = None


class MarinaResponse(BaseModel):
    id: int
    name: str
    location: Optional[str]
    timezone: str
    logo_url: Optional[str]
    pedestal_api_base_url: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MarinaAccessGrant(BaseModel):
    user_id: int
    marina_id: int
