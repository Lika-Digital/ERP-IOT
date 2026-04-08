"""
Webhook receiver — receives events from Pedestal SW instances.

POST /api/webhooks/pedestal/{marina_id}
- Validates HMAC-SHA256 signature from X-Webhook-Signature header
- On alarm event → writes to alarm_log
- On session event → writes to session_log
- Updates pedestal_cache
- Broadcasts WebSocket event to connected clients
"""
import hashlib
import hmac
import json
import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.marina import Marina
from ..models.cache import AlarmLog, SessionLog, PedestalCache
from ..services.websocket_manager import ws_manager

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _verify_signature(secret: str, body: bytes, signature_header: str) -> bool:
    """Verify HMAC-SHA256 signature — compare with 'sha256=' prefix."""
    expected = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    # Use compare_digest to prevent timing attacks
    return hmac.compare_digest(expected, signature_header)


@router.post("/pedestal/{marina_id}")
async def receive_webhook(
    marina_id: int,
    request: Request,
    x_webhook_signature: str = Header(default=""),
    db: Session = Depends(get_db),
):
    """
    Receive a webhook from a Pedestal SW instance.
    Validates HMAC signature, then persists the event and broadcasts via WebSocket.
    """
    body = await request.body()

    # Fetch marina record (needed for webhook_secret)
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")

    # Validate signature if the marina has a webhook_secret configured
    if marina.webhook_secret:
        if not x_webhook_signature:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-Webhook-Signature header",
            )
        if not _verify_signature(marina.webhook_secret, body, x_webhook_signature):
            log.warning(
                f"[WEBHOOK] Invalid signature for marina {marina_id} — "
                f"signature={x_webhook_signature[:30]}"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

    # Parse payload
    try:
        payload: Dict[str, Any] = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = payload.get("event_type", payload.get("event", "unknown"))
    pedestal_id = payload.get("pedestal_id", 0)
    now = datetime.utcnow()

    # ── 1. Update pedestal_cache ──────────────────────────────────────────────
    _update_cache(db, marina_id, pedestal_id, payload, now)

    # ── 2. Persist to event-specific log ─────────────────────────────────────
    if "alarm" in event_type.lower():
        _write_alarm_log(db, marina_id, pedestal_id, payload, now)

    if "session" in event_type.lower():
        _write_session_log(db, marina_id, pedestal_id, payload, now)

    if event_type == "temperature_reading":
        _update_temperature(db, marina_id, pedestal_id, payload, now)

    _SENSOR_EVENTS = {"power_reading", "water_reading", "moisture_reading",
                      "temperature_reading", "heartbeat", "pedestal_health_updated"}
    if event_type in _SENSOR_EVENTS:
        _update_readings(db, marina_id, pedestal_id, event_type, payload, now)

    # ── 3. Broadcast via WebSocket ────────────────────────────────────────────
    ws_message = {
        "event": "webhook_event",
        "data": {
            "marina_id": marina_id,
            "event_type": event_type,
            "payload": payload,
            "timestamp": now.isoformat(),
        },
    }
    await ws_manager.broadcast_to_marina(marina_id, ws_message)

    log.info(
        f"[WEBHOOK] Received {event_type} for marina={marina_id} pedestal={pedestal_id}"
    )
    return {"received": True, "event_type": event_type}


def _update_cache(
    db: Session, marina_id: int, pedestal_id: int, payload: dict, now: datetime
) -> None:
    if not pedestal_id:
        return
    try:
        entry = (
            db.query(PedestalCache)
            .filter(
                PedestalCache.marina_id == marina_id,
                PedestalCache.pedestal_id == pedestal_id,
            )
            .first()
        )
        if entry:
            entry.last_seen_data = payload
            entry.last_synced_at = now
            entry.is_stale = False
        else:
            entry = PedestalCache(
                marina_id=marina_id,
                pedestal_id=pedestal_id,
                last_seen_data=payload,
                last_synced_at=now,
                is_stale=False,
            )
            db.add(entry)
        db.commit()
    except Exception as exc:
        log.warning(f"[WEBHOOK] Cache update failed: {exc}")
        db.rollback()


def _update_temperature(
    db: Session, marina_id: int, pedestal_id: int, payload: dict, now: datetime
) -> None:
    """Store the latest temperature reading on the pedestal cache row."""
    # Payload may be {"event":"temperature_reading","data":{...}} or flat
    data = payload.get("data", payload)
    try:
        value = float(data.get("value", data.get("temperature", 0)))
        alarm = bool(data.get("alarm", False))
    except (TypeError, ValueError):
        return
    # Use pedestal_id=0 as marina-level sensor if no specific pedestal
    pid = pedestal_id if pedestal_id else 0
    try:
        entry = (
            db.query(PedestalCache)
            .filter(PedestalCache.marina_id == marina_id, PedestalCache.pedestal_id == pid)
            .first()
        )
        if entry:
            entry.last_temperature = value
            entry.last_temperature_alarm = alarm
            entry.last_temperature_at = now
        else:
            entry = PedestalCache(
                marina_id=marina_id,
                pedestal_id=pid,
                last_temperature=value,
                last_temperature_alarm=alarm,
                last_temperature_at=now,
                is_stale=False,
            )
            db.add(entry)
        db.commit()
    except Exception as exc:
        log.warning(f"[WEBHOOK] temperature cache update failed: {exc}")
        db.rollback()


def _update_readings(
    db: Session, marina_id: int, pedestal_id: int, event_type: str, payload: dict, now: datetime
) -> None:
    """Store latest sensor reading in the last_readings JSON blob per pedestal."""
    data = payload.get("data", payload)
    pid = pedestal_id if pedestal_id else 0

    # Build the reading entry based on event type
    if event_type == "power_reading":
        reading = {
            "watts": data.get("watts"),
            "kwh_total": data.get("kwh_total"),
            "socket_id": data.get("socket_id"),
            "at": now.isoformat(),
        }
    elif event_type == "water_reading":
        reading = {
            "lpm": data.get("lpm"),
            "total_liters": data.get("total_liters"),
            "at": now.isoformat(),
        }
    elif event_type == "moisture_reading":
        reading = {
            "value": data.get("value"),
            "alarm": data.get("alarm", False),
            "at": now.isoformat(),
        }
    elif event_type == "temperature_reading":
        reading = {
            "value": data.get("value"),
            "alarm": data.get("alarm", False),
            "at": now.isoformat(),
        }
    elif event_type in ("heartbeat", "pedestal_health_updated"):
        reading = {"at": now.isoformat(), **{k: v for k, v in data.items() if k != "pedestal_id"}}
    else:
        return

    try:
        entry = (
            db.query(PedestalCache)
            .filter(PedestalCache.marina_id == marina_id, PedestalCache.pedestal_id == pid)
            .first()
        )
        if entry:
            current = dict(entry.last_readings or {})
            current[event_type] = reading
            entry.last_readings = current
        else:
            entry = PedestalCache(
                marina_id=marina_id,
                pedestal_id=pid,
                last_readings={event_type: reading},
                is_stale=False,
            )
            db.add(entry)
        db.commit()
    except Exception as exc:
        log.warning(f"[WEBHOOK] readings cache update failed: {exc}")
        db.rollback()


def _write_alarm_log(
    db: Session, marina_id: int, pedestal_id: int, payload: dict, now: datetime
) -> None:
    try:
        entry = AlarmLog(
            marina_id=marina_id,
            pedestal_id=pedestal_id or 0,
            alarm_data=payload,
            received_at=now,
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        log.warning(f"[WEBHOOK] alarm_log write failed: {exc}")
        db.rollback()


def _write_session_log(
    db: Session, marina_id: int, pedestal_id: int, payload: dict, now: datetime
) -> None:
    try:
        entry = SessionLog(
            marina_id=marina_id,
            pedestal_id=pedestal_id or 0,
            session_data=payload,
            recorded_at=now,
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        log.warning(f"[WEBHOOK] session_log write failed: {exc}")
        db.rollback()
