"""
test_webhooks.py — Webhook receiver tests.

Verifies:
- Valid HMAC signature is accepted
- Invalid HMAC → 401
- Alarm event → written to alarm_log
- Session event → written to session_log
- WebSocket broadcast occurs on valid event
"""
import hashlib
import hmac
import json
import pytest
from unittest.mock import AsyncMock, patch


WEBHOOK_SECRET = "test-webhook-secret"


def _make_signature(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def test_valid_webhook_accepted(client, marina_id):
    payload = {
        "event_type": "sensor_update",
        "pedestal_id": 1,
        "data": {"temperature": 25.5},
    }
    body = json.dumps(payload).encode()
    sig = _make_signature(body)

    with patch("app.routers.webhooks.ws_manager.broadcast_to_marina", new_callable=AsyncMock):
        r = client.post(
            f"/api/webhooks/pedestal/{marina_id}",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": sig,
            },
        )
    assert r.status_code == 200
    assert r.json()["received"] is True


def test_invalid_signature_returns_401(client, marina_id):
    payload = {"event_type": "sensor_update", "pedestal_id": 1}
    body = json.dumps(payload).encode()

    with patch("app.routers.webhooks.ws_manager.broadcast_to_marina", new_callable=AsyncMock):
        r = client.post(
            f"/api/webhooks/pedestal/{marina_id}",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": "sha256=invalidsignature",
            },
        )
    assert r.status_code == 401


def test_missing_signature_returns_401(client, marina_id):
    payload = {"event_type": "sensor_update", "pedestal_id": 1}
    body = json.dumps(payload).encode()

    with patch("app.routers.webhooks.ws_manager.broadcast_to_marina", new_callable=AsyncMock):
        r = client.post(
            f"/api/webhooks/pedestal/{marina_id}",
            content=body,
            headers={"Content-Type": "application/json"},
        )
    assert r.status_code == 401


def test_alarm_event_written_to_alarm_log(client, marina_id, setup_test_database):
    payload = {
        "event_type": "alarm_triggered",
        "pedestal_id": 99,
        "id": 777,
        "alarm_type": "temperature",
        "value": 55.0,
    }
    body = json.dumps(payload).encode()
    sig = _make_signature(body)

    with patch("app.routers.webhooks.ws_manager.broadcast_to_marina", new_callable=AsyncMock):
        r = client.post(
            f"/api/webhooks/pedestal/{marina_id}",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": sig,
            },
        )
    assert r.status_code == 200

    # Verify alarm_log entry was created
    from tests.conftest import TestSession
    from app.models.cache import AlarmLog
    db = TestSession()
    try:
        entry = (
            db.query(AlarmLog)
            .filter(AlarmLog.marina_id == marina_id, AlarmLog.pedestal_id == 99)
            .first()
        )
        assert entry is not None
        assert entry.alarm_data["alarm_type"] == "temperature"
    finally:
        db.close()


def test_session_event_written_to_session_log(client, marina_id, setup_test_database):
    payload = {
        "event_type": "session_created",
        "pedestal_id": 88,
        "session_id": 555,
        "status": "pending",
    }
    body = json.dumps(payload).encode()
    sig = _make_signature(body)

    with patch("app.routers.webhooks.ws_manager.broadcast_to_marina", new_callable=AsyncMock):
        r = client.post(
            f"/api/webhooks/pedestal/{marina_id}",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": sig,
            },
        )
    assert r.status_code == 200

    from tests.conftest import TestSession
    from app.models.cache import SessionLog
    db = TestSession()
    try:
        entry = (
            db.query(SessionLog)
            .filter(SessionLog.marina_id == marina_id, SessionLog.pedestal_id == 88)
            .first()
        )
        assert entry is not None
        assert entry.session_data["session_id"] == 555
    finally:
        db.close()


def test_websocket_broadcast_called_on_valid_event(client, marina_id):
    payload = {"event_type": "heartbeat", "pedestal_id": 1}
    body = json.dumps(payload).encode()
    sig = _make_signature(body)

    with patch(
        "app.routers.webhooks.ws_manager.broadcast_to_marina",
        new_callable=AsyncMock
    ) as mock_broadcast:
        r = client.post(
            f"/api/webhooks/pedestal/{marina_id}",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": sig,
            },
        )
    assert r.status_code == 200
    mock_broadcast.assert_called_once()
    call_args = mock_broadcast.call_args
    assert call_args[0][0] == marina_id  # First arg = marina_id
    ws_msg = call_args[0][1]
    assert ws_msg["event"] == "webhook_event"
    assert ws_msg["data"]["marina_id"] == marina_id


def test_nonexistent_marina_returns_404(client):
    payload = {"event_type": "heartbeat", "pedestal_id": 1}
    body = json.dumps(payload).encode()
    sig = _make_signature(body)

    r = client.post(
        "/api/webhooks/pedestal/999999",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": sig,
        },
    )
    assert r.status_code == 404
