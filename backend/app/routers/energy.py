"""Energy / analytics router."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.marina import Marina
from ..models.user import User
from ..services.pedestal_api_factory import PedestalAPIClientFactory, get_pedestal_factory
from .auth import get_current_user, require_marina_access

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
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")
    require_marina_access(marina_id, user, db)

    client = factory.get_client(marina_id, db)
    data, is_stale = await client.get_daily_analytics(marina_id, db, date_from, date_to)
    return {"marina_id": marina_id, "is_stale": is_stale, "data": data}


@router.get("/{marina_id}/energy/summary")
async def get_session_summary(
    marina_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """Session summary statistics (total sessions, energy, water) from Pedestal SW."""
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")
    require_marina_access(marina_id, user, db)

    client = factory.get_client(marina_id, db)
    data, is_stale = await client.get_session_summary(marina_id, db)
    return {"marina_id": marina_id, "is_stale": is_stale, "data": data}


@router.get("/{marina_id}/sessions/active")
async def get_active_sessions(
    marina_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """Currently active sessions from Pedestal SW."""
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")
    require_marina_access(marina_id, user, db)

    client = factory.get_client(marina_id, db)
    data, is_stale = await client.get_active_sessions(marina_id, db)
    return {"marina_id": marina_id, "is_stale": is_stale, "sessions": data}


@router.get("/{marina_id}/sessions/pending")
async def get_pending_sessions(
    marina_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """Pending sessions awaiting approval from Pedestal SW."""
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")
    require_marina_access(marina_id, user, db)

    client = factory.get_client(marina_id, db)
    data, is_stale = await client.get_pending_sessions(marina_id, db)
    return {"marina_id": marina_id, "is_stale": is_stale, "sessions": data}
