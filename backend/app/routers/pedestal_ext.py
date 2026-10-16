"""
Pedestal-specific ext endpoint: berth occupancy.

The camera frame and stream routes are gone (D30, spec §6.12): no picture or video
comes from a cabinet to the ERP in phase 1.

- PREFIX  /api/marinas/{marina_id}/pedestals/{pedestal_id}/...
- Auth    get_current_user + require_marina_access
- Data    an Outcome from the cabinet client; no data at all -> 503 with the
          outcome's code and sentence (spec §2.5), never a 500
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.user import User
from ..services.pedestal_api_factory import PedestalAPIClientFactory, get_pedestal_factory
from ._cabinet import marina_client
from .auth import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marinas", tags=["pedestal-ext"])


def _data_or_503(outcome, marina_id: int, pedestal_id: int) -> dict:
    if not outcome.has_data:
        raise HTTPException(status_code=503, detail=outcome.public())
    return {"marina_id": marina_id, "pedestal_id": pedestal_id, "is_stale": outcome.is_stale,
            "outcome": outcome.public(), "data": outcome.data}


@router.get("/{marina_id}/pedestals/{pedestal_id}/berths/occupancy")
async def get_berth_occupancy(
    marina_id: int,
    pedestal_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """Fallback occupancy (occupied only). The berth view uses berths.list (§2.2)."""
    _, client = marina_client(marina_id, user, db, factory)
    return _data_or_503(await client.berth_occupancy(pedestal_id, db), marina_id, pedestal_id)
