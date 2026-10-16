"""Energy / analytics router."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.user import User
from ..services.pedestal_api_factory import PedestalAPIClientFactory, get_pedestal_factory
from ._cabinet import marina_client, read
from .auth import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marinas", tags=["energy"])


@router.get("/{marina_id}/energy/daily")
async def get_daily_analytics(
    marina_id: int,
    date_from: Optional[str] = Query(default=None, description="ISO date YYYY-MM-DD"),
    date_to: Optional[str] = Query(default=None, description="ISO date YYYY-MM-DD"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """Daily energy consumption analytics from Pedestal SW."""
    _, client = marina_client(marina_id, user, db, factory)
    # cache keyed by the date range too (spec §11 O20)
    return read(await client.daily_analytics(db, date_from, date_to), "data", marina_id=marina_id)


@router.get("/{marina_id}/energy/summary")
async def get_session_summary(
    marina_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """Session summary statistics (total sessions, energy, water) from Pedestal SW."""
    _, client = marina_client(marina_id, user, db, factory)
    return read(await client.session_summary(db), "data", marina_id=marina_id)


@router.get("/{marina_id}/sessions/active")
async def get_active_sessions(
    marina_id: int,
    cabinet: Optional[int] = Query(default=None, description="the ERP's cabinets.id (P4)"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """Currently active sessions from Pedestal SW."""
    _, client = marina_client(marina_id, user, db, factory, cabinet)
    return read(await client.active_sessions(db), "sessions", marina_id=marina_id)


@router.get("/{marina_id}/sessions/pending")
async def get_pending_sessions(
    marina_id: int,
    cabinet: Optional[int] = Query(default=None, description="the ERP's cabinets.id (P4)"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """Pending sessions awaiting approval from Pedestal SW."""
    _, client = marina_client(marina_id, user, db, factory, cabinet)
    return read(await client.pending_sessions(db), "sessions", marina_id=marina_id)
