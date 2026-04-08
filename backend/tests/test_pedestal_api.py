"""
test_pedestal_api.py — Legacy compatibility tests for PedestalAPIService alias.

PedestalAPIService is now an alias for PedestalAPIClient.  These tests verify
that the backwards-compat alias still works and that the client uses
Authorization: Bearer (not X-API-Key) in all requests.
"""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./tests/test_erp.db")
os.environ.setdefault("JWT_SECRET", "test-secret-for-erp-iot-ci")
os.environ.setdefault("ERP_ENCRYPTION_KEY", "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=")

from app.services.pedestal_api import PedestalAPIService, _update_cache, _get_cache

MOCK_BASE_URL = "http://pedestal-sw.test"
MOCK_EMAIL = "erp@service.test"
MOCK_PASSWORD = "test-service-pass"
MOCK_TOKEN = "test-bearer-token"


@pytest.fixture
def svc():
    """PedestalAPIService (alias for PedestalAPIClient) with pre-loaded token cache."""
    instance = PedestalAPIService(
        marina_id=1,
        base_url=MOCK_BASE_URL,
        service_email=MOCK_EMAIL,
        service_password=MOCK_PASSWORD,
        timeout=5.0,
    )
    # Pre-load token cache so we don't need to mock login in every test
    instance._token_cache = {
        "token": MOCK_TOKEN,
        "expires_at": datetime.utcnow() + timedelta(hours=6),
    }
    return instance


@pytest.fixture
def mock_db():
    """Mock SQLAlchemy session — always returns None from query (no cached data)."""
    db = MagicMock()
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = None
    db.query.return_value = mock_query
    return db


@pytest.mark.asyncio
async def test_bearer_header_is_sent(svc, mock_db):
    """Verify Authorization: Bearer is included in every request (not X-API-Key)."""
    captured_headers: dict = {}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        async def capture_request(method, url, **kwargs):
            captured_headers.update(kwargs.get("headers", {}))
            return MagicMock(
                status_code=200,
                json=lambda: {"pedestals": []},
                raise_for_status=lambda: None,
            )

        mock_client.request = capture_request
        mock_client_cls.return_value = mock_client

        data, is_stale = await svc.list_pedestals(marina_id=1, db=mock_db)

    assert "Authorization" in captured_headers
    assert captured_headers["Authorization"] == f"Bearer {MOCK_TOKEN}"
    # Must NOT use old X-API-Key header
    assert "X-API-Key" not in captured_headers


@pytest.mark.asyncio
async def test_returns_stale_cache_when_unreachable(svc):
    """When pedestal is unreachable, should return cached data with is_stale=True."""
    cached_data = {"pedestals": [{"id": 1, "name": "Pedestal A"}]}

    db = MagicMock()
    cache_entry = MagicMock()
    cache_entry.last_seen_data = cached_data
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = cache_entry
    db.query.return_value = mock_query

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        mock_client_cls.return_value = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            data, is_stale = await svc.list_pedestals(marina_id=1, db=db)

    assert is_stale is True
    assert data == cached_data


@pytest.mark.asyncio
async def test_returns_none_stale_when_no_cache(svc, mock_db):
    """When pedestal is unreachable and no cache exists, returns (None, True)."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        mock_client_cls.return_value = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            data, is_stale = await svc.list_pedestals(marina_id=1, db=mock_db)

    assert is_stale is True
    assert data is None


@pytest.mark.asyncio
async def test_successful_response_not_stale(svc, mock_db):
    """Successful API response should return is_stale=False."""
    mock_data = [{"id": 1, "name": "Pedestal A"}]

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.request = AsyncMock(return_value=MagicMock(
            status_code=200,
            json=lambda: mock_data,
            raise_for_status=lambda: None,
        ))
        mock_client_cls.return_value = mock_client

        data, is_stale = await svc.list_pedestals(marina_id=1, db=mock_db)

    assert is_stale is False
    assert data == mock_data


@pytest.mark.asyncio
async def test_allow_session_sends_post(svc):
    """allow_session should POST to /api/ext/controls/{id}/allow."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=MagicMock(
            status_code=200,
            json=lambda: {"status": "allowed"},
            raise_for_status=lambda: None,
        ))
        mock_client_cls.return_value = mock_client

        result = await svc.allow_session(session_id=42)
        assert result == {"status": "allowed"}

        call_args = mock_client.post.call_args
        url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
        assert "/api/ext/controls/42/allow" in url


@pytest.mark.asyncio
async def test_deny_session_sends_reason(svc):
    """deny_session should POST with reason payload."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=MagicMock(
            status_code=200,
            json=lambda: {"status": "denied"},
            raise_for_status=lambda: None,
        ))
        mock_client_cls.return_value = mock_client

        result = await svc.deny_session(session_id=5, reason="No space")
        assert result == {"status": "denied"}

        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs.get("json") == {"reason": "No space"}
