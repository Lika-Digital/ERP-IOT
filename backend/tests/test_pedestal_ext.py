"""
test_pedestal_ext.py — Tests for pedestal-specific ext endpoints.

Covers:
  TC-PX-01  berth occupancy returns structured data grouped per pedestal
  TC-PX-02  berth occupancy with empty berths returns message
  TC-PX-03  berth occupancy 503 when feature unavailable (client returns None)
  TC-PX-04  camera frame returns image/jpeg bytes with correct content-type
  TC-PX-05  camera frame 503 on service failure
  TC-PX-06  camera stream URL returns RTSP data
  TC-PX-07  camera stream 503 when unavailable
  TC-PX-08  Refresh All: multiple occupancy calls succeed independently
  TC-PX-09  marina manager blocked from restricted marina (403)
  TC-PX-10  marina manager can access own marina (200)
  TC-PX-11  unauthenticated requests return 401
  TC-PX-12  allow session logs audit + 200
  TC-PX-13  deny session logs audit + reason
  TC-PX-14  stop session logs audit
  TC-PX-15  acknowledge alarm logs audit
  TC-PX-16  camera frame proxies JPEG bytes with correct content-type
  TC-PX-17  PedestalAPIClient.get_berth_occupancy calls correct Pedestal SW path
  TC-PX-18  PedestalAPIClient.get_camera_frame retries on 5xx + raises on exhaustion
  TC-PX-19  PedestalAPIClient.get_camera_stream_url calls correct Pedestal SW path

All existing ERP tests continue to pass (no shared mutable state introduced here).
"""
import pytest
import httpx
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./tests/test_erp.db")
os.environ.setdefault("JWT_SECRET", "test-secret-for-erp-iot-ci")
os.environ.setdefault("ERP_ENCRYPTION_KEY", "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=")

from app.services.pedestal_api import PedestalAPIClient

MOCK_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"
FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # minimal JPEG magic bytes


# ─── Helper: mock factory ──────────────────────────────────────────────────────

def _make_factory(
    berth_occ_result=None,
    camera_frame_bytes=None,
    camera_frame_error=None,
    stream_result=None,
):
    """Build a PedestalAPIClientFactory mock with configurable method behaviour."""
    mock_client = MagicMock()

    if camera_frame_error:
        mock_client.get_camera_frame = AsyncMock(side_effect=camera_frame_error)
    else:
        mock_client.get_camera_frame = AsyncMock(
            return_value=camera_frame_bytes if camera_frame_bytes is not None else FAKE_JPEG
        )

    mock_client.get_berth_occupancy = AsyncMock(
        return_value=berth_occ_result if berth_occ_result is not None else (None, True)
    )
    mock_client.get_camera_stream_url = AsyncMock(
        return_value=stream_result if stream_result is not None else (None, True)
    )
    # Also wire existing methods used by other tests that may re-use the same client
    mock_client.allow_session = AsyncMock(return_value={"status": "allowed"})
    mock_client.deny_session = AsyncMock(return_value={"status": "denied"})
    mock_client.stop_session = AsyncMock(return_value={"status": "stopped"})
    mock_client.acknowledge_alarm = AsyncMock(return_value={"status": "acknowledged"})

    mock_factory = MagicMock()
    mock_factory.get_client.return_value = mock_client
    return mock_factory, mock_client


def _override_factory(app, mock_factory):
    from app.services.pedestal_api_factory import get_pedestal_factory
    app.dependency_overrides[get_pedestal_factory] = lambda: mock_factory


def _clear_overrides(app):
    app.dependency_overrides.clear()


# ─── TC-PX-01  berth occupancy — success with berths ─────────────────────────

def test_berth_occupancy_returns_structured_data(client, admin_headers, marina_id):
    berth_payload = {
        "pedestal_id": 1,
        "berths": [
            {"berth_id": 10, "berth_name": "Berth A", "occupied": True, "last_analyzed": "2026-04-11T10:00:00"},
            {"berth_id": 11, "berth_name": "Berth B", "occupied": False, "last_analyzed": "2026-04-11T10:00:00"},
        ],
    }
    mock_factory, _ = _make_factory(berth_occ_result=(berth_payload, False))
    from app.main import app
    _override_factory(app, mock_factory)

    r = client.get(f"/api/marinas/{marina_id}/pedestals/1/berths/occupancy", headers=admin_headers)
    _clear_overrides(app)

    assert r.status_code == 200
    body = r.json()
    assert body["marina_id"] == marina_id
    assert body["pedestal_id"] == 1
    assert body["is_stale"] is False
    assert len(body["data"]["berths"]) == 2
    assert body["data"]["berths"][0]["berth_id"] == 10
    assert body["data"]["berths"][0]["occupied"] is True
    assert body["data"]["berths"][1]["occupied"] is False


# ─── TC-PX-02  berth occupancy — empty berths with message ───────────────────

def test_berth_occupancy_empty_berths_shows_message(client, admin_headers, marina_id):
    berth_payload = {
        "pedestal_id": 2,
        "berths": [],
        "message": "No berth definitions found for this pedestal",
    }
    mock_factory, _ = _make_factory(berth_occ_result=(berth_payload, False))
    from app.main import app
    _override_factory(app, mock_factory)

    r = client.get(f"/api/marinas/{marina_id}/pedestals/2/berths/occupancy", headers=admin_headers)
    _clear_overrides(app)

    assert r.status_code == 200
    body = r.json()
    assert body["data"]["berths"] == []
    assert "No berth definitions" in body["data"]["message"]


# ─── TC-PX-03  berth occupancy — feature unavailable (503) ───────────────────

def test_berth_occupancy_503_when_feature_unavailable(client, admin_headers, marina_id):
    mock_factory, _ = _make_factory(berth_occ_result=(None, True))
    from app.main import app
    _override_factory(app, mock_factory)

    r = client.get(f"/api/marinas/{marina_id}/pedestals/1/berths/occupancy", headers=admin_headers)
    _clear_overrides(app)

    assert r.status_code == 503


# ─── TC-PX-04  camera frame — JPEG bytes with correct content-type ────────────

def test_camera_frame_returns_jpeg_bytes(client, admin_headers, marina_id):
    mock_factory, _ = _make_factory(camera_frame_bytes=FAKE_JPEG)
    from app.main import app
    _override_factory(app, mock_factory)

    r = client.get(f"/api/marinas/{marina_id}/pedestals/1/camera/frame", headers=admin_headers)
    _clear_overrides(app)

    assert r.status_code == 200
    assert "image/jpeg" in r.headers["content-type"]
    assert r.content == FAKE_JPEG


# ─── TC-PX-05  camera frame — 503 on service failure ─────────────────────────

def test_camera_frame_503_on_service_failure(client, admin_headers, marina_id):
    err = httpx.RequestError("Camera unavailable")
    mock_factory, _ = _make_factory(camera_frame_error=err)
    from app.main import app
    _override_factory(app, mock_factory)

    r = client.get(f"/api/marinas/{marina_id}/pedestals/1/camera/frame", headers=admin_headers)
    _clear_overrides(app)

    assert r.status_code == 503


# ─── TC-PX-16  camera frame — proxies JPEG with correct content-type ─────────

def test_camera_frame_content_type_is_image_jpeg(client, admin_headers, marina_id):
    """Alias for TC-PX-04 — explicit content-type verification per spec."""
    mock_factory, _ = _make_factory(camera_frame_bytes=FAKE_JPEG)
    from app.main import app
    _override_factory(app, mock_factory)

    r = client.get(f"/api/marinas/{marina_id}/pedestals/1/camera/frame", headers=admin_headers)
    _clear_overrides(app)

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/jpeg")
    assert r.headers.get("cache-control") == "no-store"


# ─── TC-PX-06  camera stream URL — success ────────────────────────────────────

def test_camera_stream_url_returns_rtsp_data(client, admin_headers, marina_id):
    stream_payload = {
        "pedestal_id": "MAR_KRK_ORM_01",
        "stream_url": "rtsp://192.168.1.10:554/stream",
        "reachable": True,
        "last_checked": "2026-04-11T09:00:00",
    }
    mock_factory, _ = _make_factory(stream_result=(stream_payload, False))
    from app.main import app
    _override_factory(app, mock_factory)

    r = client.get(f"/api/marinas/{marina_id}/pedestals/1/camera/stream", headers=admin_headers)
    _clear_overrides(app)

    assert r.status_code == 200
    body = r.json()
    assert body["data"]["stream_url"] == "rtsp://192.168.1.10:554/stream"
    assert body["data"]["reachable"] is True


# ─── TC-PX-07  camera stream URL — 503 when unavailable ──────────────────────

def test_camera_stream_url_503_when_unavailable(client, admin_headers, marina_id):
    mock_factory, _ = _make_factory(stream_result=(None, True))
    from app.main import app
    _override_factory(app, mock_factory)

    r = client.get(f"/api/marinas/{marina_id}/pedestals/1/camera/stream", headers=admin_headers)
    _clear_overrides(app)

    assert r.status_code == 503


# ─── TC-PX-08  Refresh All: multiple occupancy calls succeed independently ────

def test_refresh_all_occupancy_for_multiple_pedestals(client, admin_headers, marina_id):
    """Occupancy endpoint is independent per pedestal_id (no shared state)."""
    payloads = {
        1: {"pedestal_id": 1, "berths": [{"berth_id": 1, "berth_name": "A", "occupied": False}]},
        2: {"pedestal_id": 2, "berths": []},
    }

    async def side_effect_occ(pedestal_id, marina_id, db):
        return payloads.get(pedestal_id, (None, True)), False

    mock_client = MagicMock()
    mock_client.get_berth_occupancy = AsyncMock(side_effect=side_effect_occ)
    mock_factory = MagicMock()
    mock_factory.get_client.return_value = mock_client

    from app.main import app
    _override_factory(app, mock_factory)

    r1 = client.get(f"/api/marinas/{marina_id}/pedestals/1/berths/occupancy", headers=admin_headers)
    r2 = client.get(f"/api/marinas/{marina_id}/pedestals/2/berths/occupancy", headers=admin_headers)
    _clear_overrides(app)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["pedestal_id"] == 1
    assert r2.json()["pedestal_id"] == 2


# ─── TC-PX-09  marina manager blocked from restricted marina ─────────────────

def test_marina_manager_blocked_from_restricted_marina_berths(
    client, manager_headers, restricted_marina_id
):
    mock_factory, _ = _make_factory()
    from app.main import app
    _override_factory(app, mock_factory)

    for endpoint in ["berths/occupancy", "camera/frame", "camera/stream"]:
        r = client.get(
            f"/api/marinas/{restricted_marina_id}/pedestals/1/{endpoint}",
            headers=manager_headers,
        )
        assert r.status_code == 403, f"Expected 403 for {endpoint}, got {r.status_code}"

    _clear_overrides(app)


# ─── TC-PX-10  marina manager can access own marina ──────────────────────────

def test_marina_manager_can_access_own_marina_berths(client, manager_headers, marina_id):
    berth_payload = {"pedestal_id": 1, "berths": []}
    mock_factory, _ = _make_factory(berth_occ_result=(berth_payload, False))
    from app.main import app
    _override_factory(app, mock_factory)

    r = client.get(
        f"/api/marinas/{marina_id}/pedestals/1/berths/occupancy",
        headers=manager_headers,
    )
    _clear_overrides(app)
    assert r.status_code == 200


# ─── TC-PX-11  unauthenticated returns 401 ───────────────────────────────────

def test_unauthenticated_ext_endpoints_return_401(client, marina_id):
    # Security middleware may return 403 or FastAPI bearer returns 401; both signal unauthenticated.
    for endpoint in ["berths/occupancy", "camera/frame", "camera/stream"]:
        r = client.get(f"/api/marinas/{marina_id}/pedestals/1/{endpoint}")
        assert r.status_code in (401, 403), (
            f"Expected 401 or 403 for {endpoint}, got {r.status_code}"
        )


# ─── TC-PX-12  allow session logs audit ──────────────────────────────────────

def test_allow_session_controls_tab_logs_audit(client, admin_headers, marina_id, setup_test_database):
    """Controls tab allow calls the existing allow endpoint — verify audit log written."""
    mock_factory, _ = _make_factory()
    from app.main import app
    _override_factory(app, mock_factory)

    r = client.post(
        f"/api/marinas/{marina_id}/sessions/100/allow",
        headers=admin_headers,
        params={"pedestal_id": 1},
    )
    _clear_overrides(app)

    assert r.status_code == 200

    from tests.conftest import TestSession
    from app.models.cache import AuditLog
    db = TestSession()
    try:
        entry = (
            db.query(AuditLog)
            .filter(AuditLog.marina_id == marina_id, AuditLog.action == "allow_session", AuditLog.target_id == 100)
            .order_by(AuditLog.performed_at.desc())
            .first()
        )
        assert entry is not None
        assert entry.pedestal_id == 1
    finally:
        db.close()


# ─── TC-PX-13  deny session logs audit ───────────────────────────────────────

def test_deny_session_controls_tab_logs_audit_with_reason(client, admin_headers, marina_id, setup_test_database):
    mock_factory, _ = _make_factory()
    from app.main import app
    _override_factory(app, mock_factory)

    r = client.post(
        f"/api/marinas/{marina_id}/sessions/101/deny",
        headers=admin_headers,
        json={"reason": "No berth available"},
        params={"pedestal_id": 1},
    )
    _clear_overrides(app)

    assert r.status_code == 200

    from tests.conftest import TestSession
    from app.models.cache import AuditLog
    db = TestSession()
    try:
        entry = (
            db.query(AuditLog)
            .filter(AuditLog.marina_id == marina_id, AuditLog.action == "deny_session", AuditLog.target_id == 101)
            .order_by(AuditLog.performed_at.desc())
            .first()
        )
        assert entry is not None
        assert entry.details["reason"] == "No berth available"
    finally:
        db.close()


# ─── TC-PX-14  stop session logs audit ───────────────────────────────────────

def test_stop_session_controls_tab_logs_audit(client, admin_headers, marina_id, setup_test_database):
    mock_factory, _ = _make_factory()
    from app.main import app
    _override_factory(app, mock_factory)

    r = client.post(
        f"/api/marinas/{marina_id}/sessions/102/stop",
        headers=admin_headers,
        params={"pedestal_id": 1},
    )
    _clear_overrides(app)

    assert r.status_code == 200

    from tests.conftest import TestSession
    from app.models.cache import AuditLog
    db = TestSession()
    try:
        entry = (
            db.query(AuditLog)
            .filter(AuditLog.marina_id == marina_id, AuditLog.action == "stop_session", AuditLog.target_id == 102)
            .order_by(AuditLog.performed_at.desc())
            .first()
        )
        assert entry is not None
    finally:
        db.close()


# ─── TC-PX-15  acknowledge alarm logs audit ──────────────────────────────────

def test_acknowledge_alarm_controls_tab_logs_audit(client, admin_headers, marina_id, setup_test_database):
    mock_factory, _ = _make_factory()
    from app.main import app
    _override_factory(app, mock_factory)

    r = client.post(
        f"/api/marinas/{marina_id}/alarms/50/acknowledge",
        headers=admin_headers,
        params={"pedestal_id": 1},
    )
    _clear_overrides(app)

    assert r.status_code == 200
    body = r.json()
    assert body["acknowledged"] is True
    assert body["alarm_id"] == 50

    from tests.conftest import TestSession
    from app.models.cache import AuditLog
    db = TestSession()
    try:
        entry = (
            db.query(AuditLog)
            .filter(
                AuditLog.marina_id == marina_id,
                AuditLog.action == "acknowledge_alarm",
                AuditLog.target_id == 50,
            )
            .order_by(AuditLog.performed_at.desc())
            .first()
        )
        assert entry is not None
        assert entry.pedestal_id == 1
    finally:
        db.close()


# ─── TC-PX-17  PedestalAPIClient.get_berth_occupancy uses correct path ────────

@pytest.mark.asyncio
async def test_api_client_get_berth_occupancy_correct_path():
    """Verify that get_berth_occupancy calls /api/ext/pedestals/{id}/berths/occupancy."""
    client = PedestalAPIClient(
        marina_id=1,
        base_url="http://pedestal-sw.test",
        service_email="svc@test.local",
        service_password="secret",
    )
    client._token_cache = {
        "token": MOCK_TOKEN,
        "expires_at": datetime.utcnow() + timedelta(hours=6),
    }
    captured_urls: list = []

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        async def fake_request(method, url, **kwargs):
            captured_urls.append(url)
            return MagicMock(status_code=200, json=lambda: {"berths": []}, raise_for_status=lambda: None)

        mock_http.request = fake_request
        mock_cls.return_value = mock_http

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        data, is_stale = await client.get_berth_occupancy(pedestal_id=5, marina_id=1, db=db)

    assert len(captured_urls) == 1
    assert "/api/ext/pedestals/5/berths/occupancy" in captured_urls[0]
    assert is_stale is False


# ─── TC-PX-18  PedestalAPIClient.get_camera_frame retries + raises ───────────

@pytest.mark.asyncio
async def test_api_client_get_camera_frame_retries_and_raises():
    """get_camera_frame must retry _MAX_RETRIES times on 5xx, then raise."""
    client = PedestalAPIClient(
        marina_id=1,
        base_url="http://pedestal-sw.test",
        service_email="svc@test.local",
        service_password="secret",
    )
    client._token_cache = {
        "token": MOCK_TOKEN,
        "expires_at": datetime.utcnow() + timedelta(hours=6),
    }
    call_count = 0

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        async def fail_5xx(url, **kwargs):
            nonlocal call_count
            call_count += 1
            err_resp = MagicMock()
            err_resp.status_code = 503
            err_resp.text = "Service Unavailable"
            raise httpx.HTTPStatusError("503", request=MagicMock(), response=err_resp)

        mock_http.get = fail_5xx
        mock_cls.return_value = mock_http

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(httpx.RequestError):
                await client.get_camera_frame(pedestal_id=1, marina_id=1, db=None)

    assert call_count == 3


# ─── TC-PX-19  PedestalAPIClient.get_camera_stream_url uses correct path ──────

@pytest.mark.asyncio
async def test_api_client_get_camera_stream_url_correct_path():
    """Verify that get_camera_stream_url calls /api/ext/pedestals/{id}/camera/stream."""
    client = PedestalAPIClient(
        marina_id=1,
        base_url="http://pedestal-sw.test",
        service_email="svc@test.local",
        service_password="secret",
    )
    client._token_cache = {
        "token": MOCK_TOKEN,
        "expires_at": datetime.utcnow() + timedelta(hours=6),
    }
    captured_urls: list = []

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        async def fake_request(method, url, **kwargs):
            captured_urls.append(url)
            return MagicMock(
                status_code=200,
                json=lambda: {"stream_url": "rtsp://x", "reachable": True, "last_checked": None},
                raise_for_status=lambda: None,
            )

        mock_http.request = fake_request
        mock_cls.return_value = mock_http

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        data, is_stale = await client.get_camera_stream_url(pedestal_id=7, marina_id=1, db=db)

    assert len(captured_urls) == 1
    assert "/api/ext/pedestals/7/camera/stream" in captured_urls[0]
    assert is_stale is False
