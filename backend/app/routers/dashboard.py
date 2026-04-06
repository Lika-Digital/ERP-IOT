"""Dashboard router — aggregated marina overview data."""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.marina import Marina
from ..models.user import User
from ..services.pedestal_api import PedestalAPIService
from .auth import get_current_user, require_marina_access

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marinas", tags=["dashboard"])


def _get_api_service(marina: Marina) -> PedestalAPIService:
    return PedestalAPIService(marina.pedestal_api_base_url, marina.pedestal_api_key)


@router.get("/{marina_id}/dashboard")
async def get_dashboard(
    marina_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Aggregated dashboard: pedestals, health, active sessions, pending sessions.
    Returns is_stale=True if any data came from cache.
    """
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")
    require_marina_access(marina_id, user, db)

    svc = _get_api_service(marina)

    pedestals_data, stale1 = await svc.list_pedestals(marina_id, db)
    health_data, stale2 = await svc.get_health(marina_id, db)
    active_data, stale3 = await svc.get_active_sessions(marina_id, db)
    pending_data, stale4 = await svc.get_pending_sessions(marina_id, db)

    is_stale = any([stale1, stale2, stale3, stale4])

    return {
        "marina_id": marina_id,
        "marina_name": marina.name,
        "is_stale": is_stale,
        "pedestals": pedestals_data,
        "health": health_data,
        "active_sessions": active_data,
        "pending_sessions": pending_data,
    }


@router.get("/{marina_id}/health")
async def get_health(
    marina_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Health check for a specific marina's Pedestal SW."""
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")
    require_marina_access(marina_id, user, db)

    svc = _get_api_service(marina)
    data, is_stale = await svc.get_health(marina_id, db)
    return {"marina_id": marina_id, "is_stale": is_stale, "data": data}


@router.get("/{marina_id}/pedestals")
async def list_pedestals(
    marina_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all pedestals for a marina."""
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")
    require_marina_access(marina_id, user, db)

    svc = _get_api_service(marina)
    data, is_stale = await svc.list_pedestals(marina_id, db)
    return {"marina_id": marina_id, "is_stale": is_stale, "pedestals": data}


@router.get("/{marina_id}/berths")
async def list_berths(
    marina_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List berth occupancy for a marina."""
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")
    require_marina_access(marina_id, user, db)

    svc = _get_api_service(marina)
    data, is_stale = await svc.list_berths(marina_id, db)
    return {"marina_id": marina_id, "is_stale": is_stale, "berths": data}
