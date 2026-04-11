"""
Pedestal-specific ext endpoints: berth occupancy, camera frame, camera stream URL.

All three endpoints follow the same pattern as controls.py:
- PREFIX  /api/marinas/{marina_id}/pedestals/{pedestal_id}/...
- Auth    get_current_user + require_marina_access
- Audit   record_action for camera frame (operator request logged)
- Stale   berth_occupancy and camera_stream_url propagate is_stale flag
- Frame   proxied as raw image/jpeg bytes; raises 503 on failure
"""
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.marina import Marina
from ..models.user import User
from ..services.audit_log import record_action
from ..services.pedestal_api_factory import PedestalAPIClientFactory, get_pedestal_factory
from .auth import get_current_user, require_marina_access

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marinas", tags=["pedestal-ext"])


def _require_marina(marina_id: int, user: User, db: Session) -> Marina:
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")
    require_marina_access(marina_id, user, db)
    return marina


# ── 1. Berth occupancy ────────────────────────────────────────────────────────

@router.get("/{marina_id}/pedestals/{pedestal_id}/berths/occupancy")
async def get_berth_occupancy(
    marina_id: int,
    pedestal_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """
    Return current berth occupancy for a specific pedestal.
    503 when feature unavailable on the Pedestal SW (data is None after all retries).
    """
    _require_marina(marina_id, user, db)
    client = factory.get_client(marina_id, db)

    try:
        data, is_stale = await client.get_berth_occupancy(pedestal_id, marina_id, db)
    except Exception as exc:
        log.error(f"[EXT] berth_occupancy pedestal={pedestal_id} error: {exc}")
        raise HTTPException(status_code=503, detail="Berth occupancy unavailable") from exc

    if data is None:
        raise HTTPException(status_code=503, detail="Berth occupancy unavailable")

    log.info(
        f"[EXT] berth_occupancy marina={marina_id} pedestal={pedestal_id} "
        f"user={user.id} stale={is_stale}"
    )
    return {
        "marina_id": marina_id,
        "pedestal_id": pedestal_id,
        "is_stale": is_stale,
        "data": data,
    }


# ── 2. Camera frame ───────────────────────────────────────────────────────────

@router.get("/{marina_id}/pedestals/{pedestal_id}/camera/frame")
async def get_camera_frame(
    marina_id: int,
    pedestal_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """
    Proxy a live JPEG frame from the pedestal camera.
    Returns Content-Type: image/jpeg.  503 when camera unavailable.
    Frame fetch is logged to audit_log (operator-initiated action).
    """
    _require_marina(marina_id, user, db)
    client = factory.get_client(marina_id, db)

    try:
        frame_bytes = await client.get_camera_frame(pedestal_id, marina_id, db)
    except (httpx.RequestError, httpx.HTTPStatusError, Exception) as exc:
        log.warning(f"[EXT] camera_frame pedestal={pedestal_id} error: {exc}")
        raise HTTPException(
            status_code=503,
            detail=f"Camera frame unavailable: {exc}",
        ) from exc

    record_action(
        db,
        user_id=user.id,
        marina_id=marina_id,
        action="get_camera_frame",
        pedestal_id=pedestal_id,
        details={"bytes": len(frame_bytes)},
    )
    log.info(
        f"[EXT] camera_frame marina={marina_id} pedestal={pedestal_id} "
        f"user={user.id} bytes={len(frame_bytes)}"
    )
    return Response(
        content=frame_bytes,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


# ── 3. Camera stream URL ──────────────────────────────────────────────────────

@router.get("/{marina_id}/pedestals/{pedestal_id}/camera/stream")
async def get_camera_stream_url(
    marina_id: int,
    pedestal_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """
    Return the RTSP stream URL for a pedestal camera plus reachability.
    Does not proxy the stream — caller connects directly.
    503 when camera not configured or Pedestal SW unreachable.
    """
    _require_marina(marina_id, user, db)
    client = factory.get_client(marina_id, db)

    try:
        data, is_stale = await client.get_camera_stream_url(pedestal_id, marina_id, db)
    except Exception as exc:
        log.error(f"[EXT] camera_stream pedestal={pedestal_id} error: {exc}")
        raise HTTPException(status_code=503, detail="Camera stream URL unavailable") from exc

    if data is None:
        raise HTTPException(status_code=503, detail="Camera stream URL unavailable")

    log.info(
        f"[EXT] camera_stream marina={marina_id} pedestal={pedestal_id} "
        f"user={user.id} stale={is_stale}"
    )
    return {
        "marina_id": marina_id,
        "pedestal_id": pedestal_id,
        "is_stale": is_stale,
        "data": data,
    }
