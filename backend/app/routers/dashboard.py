"""Dashboard router — aggregated marina overview data."""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.marina import Marina
from ..models.user import User
from ..models.cache import PedestalCache
from ..services.pedestal_api_factory import PedestalAPIClientFactory, get_pedestal_factory
from .auth import get_current_user, require_marina_access

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marinas", tags=["dashboard"])


@router.get("/{marina_id}/dashboard")
async def get_dashboard(
    marina_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """
    Aggregated dashboard: pedestals, health, active sessions, pending sessions.
    Returns is_stale=True if any data came from cache.
    """
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")
    require_marina_access(marina_id, user, db)

    client = factory.get_client(marina_id, db)

    pedestals_data, stale1 = await client.list_pedestals(marina_id, db)
    health_data, stale2 = await client.get_health(marina_id, db)
    active_data, stale3 = await client.get_active_sessions(marina_id, db)
    pending_data, stale4 = await client.get_pending_sessions(marina_id, db)

    is_stale = any([stale1, stale2, stale3, stale4])

    # Build temperature map from pedestal cache (updated by webhooks)
    cache_rows = (
        db.query(PedestalCache)
        .filter(PedestalCache.marina_id == marina_id)
        .all()
    )
    temperature_map = {
        row.pedestal_id: {
            "value": row.last_temperature,
            "alarm": row.last_temperature_alarm,
            "at": row.last_temperature_at.isoformat() if row.last_temperature_at else None,
        }
        for row in cache_rows
        if row.last_temperature is not None
    }

    return {
        "marina_id": marina_id,
        "marina_name": marina.name,
        "is_stale": is_stale,
        "pedestals": pedestals_data,
        "health": health_data,
        "active_sessions": active_data,
        "pending_sessions": pending_data,
        "temperature_map": temperature_map,
    }


@router.get("/{marina_id}/health")
async def get_health(
    marina_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """Health check for a specific marina's Pedestal SW."""
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")
    require_marina_access(marina_id, user, db)

    client = factory.get_client(marina_id, db)
    data, is_stale = await client.get_health(marina_id, db)
    return {"marina_id": marina_id, "is_stale": is_stale, "data": data}


@router.get("/{marina_id}/pedestals")
async def list_pedestals(
    marina_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """List all pedestals for a marina."""
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")
    require_marina_access(marina_id, user, db)

    client = factory.get_client(marina_id, db)
    data, is_stale = await client.list_pedestals(marina_id, db)
    return {"marina_id": marina_id, "is_stale": is_stale, "pedestals": data}


@router.get("/{marina_id}/berths")
async def list_berths(
    marina_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """List berth occupancy for a marina."""
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")
    require_marina_access(marina_id, user, db)

    client = factory.get_client(marina_id, db)
    data, is_stale = await client.list_berths(marina_id, db)
    return {"marina_id": marina_id, "is_stale": is_stale, "berths": data}
