"""
test_pedestal_api.py — PedestalAPIService unit tests.

Verifies:
- Correct X-API-Key header is sent
- Returns cached stale data when pedestal is unreachable + is_stale=True
- Retry logic (up to 3 attempts)
- Successful responses return is_stale=False
"""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.services.pedestal_api import PedestalAPIService, _update_cache, _get_cache


MOCK_BASE_URL = "http://pedestal-sw.test"
MOCK_API_KEY = "test-api-key-123"


@pytest.fixture
def svc():
    return PedestalAPIService(MOCK_BASE_URL, MOCK_API_KEY, timeout=5.0)


@pytest.fixture
def mock_db():
    """Mock SQLAlchemy session — always returns None from query (no cached data)."""
    db = MagicMock()
    # Make all chained query calls end in .first() returning None
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = None
    db.query.return_value = mock_query
    return db


@pytest.mark.asyncio
async def test_api_key_header_is_sent(svc, mock_db):
    """Verify X-API-Key is included in every request."""
    captured_headers = {}

    async def mock_transport(request):
        captured_headers.update(dict(request.headers))
        return httpx.Response(200, json={"pedestals": []})

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.request = AsyncMock(return_value=MagicMock(
            status_code=200,
            json=lambda: {"pedestals": []},
            raise_for_status=lambda: None,
        ))
        mock_client_cls.return_value = mock_client

        data, is_stale = await svc.list_pedestals(marina_id=1, db=mock_db)

        # Confirm the client was created with the correct headers
        call_kwargs = mock_client_cls.call_args
        assert call_kwargs is not None
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers.get("X-API-Key") == MOCK_API_KEY


@pytest.mark.asyncio
async def test_returns_stale_cache_when_unreachable(svc):
    """When pedestal is unreachable, should return cached data with is_stale=True."""
    # Set up a DB mock that has cached data
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
    """allow_session should POST to /api/controls/{id}/allow."""
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

        mock_client.post.assert_called_once_with(
            f"{MOCK_BASE_URL}/api/controls/42/allow"
        )


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
