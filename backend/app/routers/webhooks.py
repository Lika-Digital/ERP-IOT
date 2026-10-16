"""
Webhook receivers.

POST /api/webhooks/cabinet/{cabinet_id}   (phase 4, spec §5.2) — what the cabinet sends
  - auth: the X-API-Key this cabinet sends (cabinets.webhook_key_enc), compared in
    constant time. No key stored, an empty header, a wrong key or an unknown
    cabinet: the same 401 — the cabinet sends an EMPTY key when none is set on
    its side (NALAZ 6.1), and an unknown id must not be told apart from a bad key;
  - ready for HMAC: cabinets.webhook_hmac switches on the X-Webhook-Signature
    check, per cabinet, without an ERP release (§7.2 R3);
  - body capped (settings.webhook_max_body_bytes) — a public write path must not
    grow the database at someone else's pace;
  - for SPEED only (D7): a session payload updates the ERP session through the
    same function the reconciler uses, but never marks it reconciled; alarms go
    to alarm_log once per cabinet alarm id; everything else is counted, not stored.

POST /api/webhooks/pedestal/{marina_id}  (before phase 4) — kept for compatibility,
  HMAC with marinas.webhook_secret. Since phase 4 it FAILS CLOSED: a marina with
  no secret refuses everything (it used to accept unsigned writes).
"""
import hashlib
import hmac
import json
import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from sqlalchemy.exc import IntegrityError

from ..config import settings
from ..database import get_db
from ..models.cabinet import Cabinet
from ..models.marina import Marina
from ..models.cache import AlarmLog, SessionLog, PedestalCache
from ..services import decoys, session_sync
from ..services.pedestal_api import _write_sync_log
from ..services.websocket_manager import ws_manager
from ..utils.encryption import decrypt_password
from ..utils.time import utcnow

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
    body = await _capped_body(request)

    # Fetch marina record (needed for webhook_secret)
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")

    # Fail closed (phase 4): no secret, no writes. Before, a marina without a
    # secret accepted anything from anyone.
    if not marina.webhook_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Webhook not configured for this marina")
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
    now = utcnow()

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


# ─── Phase 4: per-cabinet receiver ────────────────────────────────────────────

# v21 (§2.6, revision item 4): the names the cabinet's ERP sender uses
# (Cloud_IOT mqtt_handlers.py:1947, 2073, 2147, 2194)
SESSION_EVENTS = {"session_activated", "telemetry", "session_ended"}
ALARM_EVENTS = {"hardware_alarm", "breaker_alarm", "meter_load_auto_stop",
                "meter_load_critical", "valve_flow_warning", "marina_door"}
_REFUSED = "Invalid or missing webhook credentials"
_NO_KEY = "\x00no-key\x00"     # compared against when nothing is stored: same cost


async def _capped_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.webhook_max_body_bytes:
        raise HTTPException(status_code=413, detail="Webhook body too large")
    body = await request.body()
    if len(body) > settings.webhook_max_body_bytes:
        raise HTTPException(status_code=413, detail="Webhook body too large")
    return body


def _cabinet_authenticated(db: Session, cabinet_id: int, api_key: str, signature: str,
                           body: bytes) -> Cabinet:
    cab = db.get(Cabinet, cabinet_id)
    expected = None
    if cab is not None and cab.webhook_key_enc:
        try:
            expected = decrypt_password(cab.webhook_key_enc)
        except ValueError:
            expected = None
    # one comparison whatever happened above, so an unknown cabinet costs the same
    same = hmac.compare_digest((expected or _NO_KEY).encode(), (api_key or "").encode())
    if not same or not api_key or expected is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_REFUSED)
    if cab.webhook_hmac:
        try:
            secret = decrypt_password(cab.webhook_secret_enc)
        except (ValueError, TypeError):
            secret = None
        if not secret or not signature or not _verify_signature(secret, body, signature):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_REFUSED)
    return cab


def _refuse_shape(db: Session, cab: Cabinet, why: str, payload) -> None:
    """v21 (§2.6): a shape the ERP does not know is refused and recorded — never parsed
    "tolerantly". The pull stays the truth (D7). The record names the shape (event,
    top-level keys), never the payload: it may carry a customer reference."""
    event = payload.get("event") if isinstance(payload, dict) else None
    keys = sorted(str(k)[:40] for k in payload)[:20] if isinstance(payload, dict) else []
    shape = f"{why}; event={str(event)[:60]!r}; keys={keys}"
    now = utcnow()
    _write_sync_log(db, cab.marina_id, "webhook.cabinet", "error", now, now, shape[:500])
    log.warning("[WEBHOOK] cabinet=%s refused: %s", cab.display_id, shape)
    raise HTTPException(status_code=422, detail={
        "code": "unknown_shape",
        "sentence": "The ERP does not know this webhook shape; it was recorded and refused.",
        "reason": why})


@router.post("/cabinet/{cabinet_id}")
async def receive_cabinet_webhook(
    cabinet_id: int,
    request: Request,
    x_api_key: str = Header(default=""),
    x_webhook_signature: str = Header(default=""),
    db: Session = Depends(get_db),
):
    body = await _capped_body(request)
    decoy = decoys.decoy_key_name(x_api_key)
    if decoy:                         # layer 2: recorded, then refused like any wrong key
        decoys.record(db, "api_key", decoy, request)
    cab = _cabinet_authenticated(db, cabinet_id, x_api_key, x_webhook_signature, body)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    if not isinstance(payload, dict) or not isinstance(payload.get("event"), str):
        _refuse_shape(db, cab, "no event", payload)
    event = payload["event"]
    if event not in SESSION_EVENTS | ALARM_EVENTS:
        _refuse_shape(db, cab, "unknown event", payload)
    if not isinstance(payload.get("data"), dict):
        _refuse_shape(db, cab, "no data object", payload)
    data = payload["data"]
    if event in SESSION_EVENTS and "session_id" not in data:
        _refuse_shape(db, cab, "session event without session_id in data", payload)
    now = utcnow()
    stored = "nothing"

    if event in SESSION_EVENTS:
        db.add(SessionLog(marina_id=cab.marina_id, pedestal_id=cab.pedestal_pk,
                          session_data=payload, recorded_at=now))
        # speed only: the same function as the pull, but never "reconciled" (D7)
        result = session_sync.apply(db, cab, data, final_by_pull=False, now=now)
        db.commit()
        stored = f"session_log; erp session: {result}"
    elif event in ALARM_EVENTS:
        alarm_id = data.get("id") if isinstance(data.get("id"), int) else None
        if alarm_id is not None and db.query(AlarmLog.id).filter(
                AlarmLog.cabinet_id == cab.id, AlarmLog.cabinet_alarm_id == alarm_id).first():
            stored = "alarm_log: already known"
        else:
            db.add(AlarmLog(marina_id=cab.marina_id, pedestal_id=cab.pedestal_pk,
                            alarm_data=payload, received_at=now, cabinet_id=cab.id,
                            cabinet_alarm_id=alarm_id, source="webhook"))
            try:
                db.commit()
                stored = "alarm_log"
            except IntegrityError:
                db.rollback()
                stored = "alarm_log: already known"

    await ws_manager.broadcast_to_marina(cab.marina_id, {
        "event": "webhook_event",
        "data": {"marina_id": cab.marina_id, "cabinet_id": cab.id, "event_type": event,
                 "payload": payload, "timestamp": now.isoformat()},
    })
    log.info("[WEBHOOK] cabinet=%s event=%s stored=%s", cab.display_id, event, stored)
    return {"received": True, "event": event, "stored": stored}
