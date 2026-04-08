"""
test_pedestal_client.py — PedestalAPIClient + encryption + factory unit tests.

Covers (Step 11 spec):
- encrypt/decrypt are inverse, no plaintext stored
- _get_token returns cached token if not expired
- _get_token calls login and caches on expiry
- _get_token raises PedestalAuthError on failed login
- _request uses Authorization: Bearer header
- _request prefixes paths with /api/ext/
- _request retries 3x on 5xx with backoff (backoff stubbed)
- _request returns stale tuple on all failures
- StaleResponse has is_stale=True, last_synced_at=None when no cache
- Factory returns same instance for same marina_id
"""
import pytest
import httpx
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure test env vars are set before importing app modules
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./tests/test_erp.db")
os.environ.setdefault("JWT_SECRET", "test-secret-for-erp-iot-ci")
os.environ.setdefault("ERP_ENCRYPTION_KEY", "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=")

from app.services.pedestal_api import (
    PedestalAPIClient,
    PedestalAuthError,
    StaleResponse,
    _update_cache,
    _get_cache,
)
from app.utils.encryption import encrypt_password, decrypt_password


MOCK_BASE_URL = "http://pedestal-sw.test"
MOCK_EMAIL = "erp@service.test"
MOCK_PASSWORD = "test-service-password"
MOCK_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"


# ─── Encryption tests ──────────────────────────────────────────────────────────

def test_encrypt_decrypt_inverse():
    """encrypt_password and decrypt_password are inverse operations."""
    plain = "my-super-secret-password!"
    encrypted = encrypt_password(plain)
    assert decrypt_password(encrypted) == plain


def test_encrypted_does_not_contain_plaintext():
    """The encrypted blob must not contain the plaintext password."""
    plain = "plaintext-password-12345"
    encrypted = encrypt_password(plain)
    assert plain not in encrypted


def test_different_encryptions_for_same_input():
    """Fernet uses random IV so two encryptions of the same value differ."""
    plain = "same-password"
    enc1 = encrypt_password(plain)
    enc2 = encrypt_password(plain)
    assert enc1 != enc2  # different nonces
    # But both decrypt to the same value
    assert decrypt_password(enc1) == decrypt_password(enc2) == plain


def test_decrypt_raises_on_tampered_data():
    """Decrypting a tampered ciphertext must raise ValueError."""
    encrypted = encrypt_password("original")
    tampered = encrypted[:-5] + "XXXXX"
    with pytest.raises(ValueError, match="decrypt"):
        decrypt_password(tampered)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    return PedestalAPIClient(
        marina_id=1,
        base_url=MOCK_BASE_URL,
        service_email=MOCK_EMAIL,
        service_password=MOCK_PASSWORD,
        timeout=5.0,
    )


@pytest.fixture
def mock_db():
    """Mock SQLAlchemy session — no cached data by default."""
    db = MagicMock()
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = None
    db.query.return_value = mock_query
    return db


# ─── Token tests ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_token_returns_cached_if_not_expired(client):
    """_get_token returns the cached token without re-authenticating."""
    # Pre-populate cache with a non-expired token
    client._token_cache = {
        "token": MOCK_TOKEN,
        "expires_at": datetime.utcnow() + timedelta(hours=6),
    }
    with patch("httpx.AsyncClient") as mock_cls:
        token = await client._get_token()
    assert token == MOCK_TOKEN
    mock_cls.assert_not_called()


@pytest.mark.asyncio
async def test_get_token_calls_login_on_empty_cache(client):
    """_get_token calls /api/auth/service-token when cache is empty."""
    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.post = AsyncMock(return_value=MagicMock(
            status_code=200,
            json=lambda: {"access_token": MOCK_TOKEN, "token_type": "bearer", "role": "api_client", "email": MOCK_EMAIL},
            raise_for_status=lambda: None,
        ))
        mock_cls.return_value = mock_http

        token = await client._get_token()

    assert token == MOCK_TOKEN
    assert client._token_cache["token"] == MOCK_TOKEN
    assert client._token_cache["expires_at"] > datetime.utcnow()


@pytest.mark.asyncio
async def test_get_token_refreshes_on_expiry(client):
    """_get_token re-authenticates when cached token is past expiry."""
    client._token_cache = {
        "token": "old-token",
        "expires_at": datetime.utcnow() - timedelta(seconds=1),  # expired
    }
    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.post = AsyncMock(return_value=MagicMock(
            status_code=200,
            json=lambda: {"access_token": MOCK_TOKEN, "token_type": "bearer", "role": "api_client", "email": MOCK_EMAIL},
            raise_for_status=lambda: None,
        ))
        mock_cls.return_value = mock_http

        token = await client._get_token()

    assert token == MOCK_TOKEN


@pytest.mark.asyncio
async def test_get_token_raises_pedestal_auth_error_on_401(client):
    """_get_token raises PedestalAuthError when server returns 401."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_cls.return_value = mock_http

        with pytest.raises(PedestalAuthError) as exc_info:
            await client._get_token()

    assert exc_info.value.marina_id == 1
    assert "401" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_token_raises_on_connection_error(client):
    """_get_token raises PedestalAuthError on network failure."""
    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_cls.return_value = mock_http

        with pytest.raises(PedestalAuthError):
            await client._get_token()


# ─── Request tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_request_uses_bearer_header(client, mock_db):
    """_request must send Authorization: Bearer <token>."""
    client._token_cache = {
        "token": MOCK_TOKEN,
        "expires_at": datetime.utcnow() + timedelta(hours=6),
    }
    captured_headers: dict = {}

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        async def fake_request(method, url, **kwargs):
            captured_headers.update(kwargs.get("headers", {}))
            return MagicMock(
                status_code=200,
                json=lambda: [],
                raise_for_status=lambda: None,
            )

        mock_http.request = fake_request
        mock_cls.return_value = mock_http

        await client._request("GET", "/api/ext/pedestals", 1, mock_db, "list_pedestals")

    assert captured_headers.get("Authorization") == f"Bearer {MOCK_TOKEN}"


@pytest.mark.asyncio
async def test_request_prefixes_api_ext(client, mock_db):
    """_request must prefix path with /api/ext/ if not already present."""
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
                json=lambda: [],
                raise_for_status=lambda: None,
            )

        mock_http.request = fake_request
        mock_cls.return_value = mock_http

        # Call with a bare path (no /api/ext/ prefix)
        await client._request("GET", "pedestals", 1, mock_db, "list_pedestals")

    assert captured_urls, "No URL captured"
    assert "/api/ext/" in captured_urls[0], f"Expected /api/ext/ in URL, got {captured_urls[0]}"


@pytest.mark.asyncio
async def test_request_retries_3x_on_5xx(client, mock_db):
    """_request retries up to _MAX_RETRIES times on 5xx responses."""
    client._token_cache = {
        "token": MOCK_TOKEN,
        "expires_at": datetime.utcnow() + timedelta(hours=6),
    }
    call_count = 0

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        async def fail_with_5xx(method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            err_resp = MagicMock()
            err_resp.status_code = 503
            err_resp.text = "Service Unavailable"
            raise httpx.HTTPStatusError("503", request=MagicMock(), response=err_resp)

        mock_http.request = fail_with_5xx
        mock_cls.return_value = mock_http

        with patch("asyncio.sleep", new_callable=AsyncMock):  # skip actual delays
            data, is_stale = await client._request(
                "GET", "/api/ext/pedestals", 1, mock_db, "list_pedestals"
            )

    # Should have tried 3 times
    assert call_count == 3
    assert is_stale is True


@pytest.mark.asyncio
async def test_request_returns_stale_none_when_no_cache(client, mock_db):
    """When all retries fail and no cache exists, returns (None, True)."""
    client._token_cache = {
        "token": MOCK_TOKEN,
        "expires_at": datetime.utcnow() + timedelta(hours=6),
    }

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        mock_cls.return_value = mock_http

        with patch("asyncio.sleep", new_callable=AsyncMock):
            data, is_stale = await client._request(
                "GET", "/api/ext/pedestals", 1, mock_db, "list_pedestals"
            )

    assert is_stale is True
    assert data is None


@pytest.mark.asyncio
async def test_request_returns_stale_cache_on_failure(client):
    """When all retries fail, _request returns cached data with is_stale=True."""
    client._token_cache = {
        "token": MOCK_TOKEN,
        "expires_at": datetime.utcnow() + timedelta(hours=6),
    }
    cached_data = [{"id": 1, "name": "Pedestal A"}]

    db = MagicMock()
    cache_entry = MagicMock()
    cache_entry.last_seen_data = cached_data
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = cache_entry
    db.query.return_value = mock_query

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        mock_cls.return_value = mock_http

        with patch("asyncio.sleep", new_callable=AsyncMock):
            data, is_stale = await client._request(
                "GET", "/api/ext/pedestals", 1, db, "list_pedestals"
            )

    assert is_stale is True
    assert data == cached_data


@pytest.mark.asyncio
async def test_list_pedestals_success_returns_not_stale(client, mock_db):
    """Successful list_pedestals call returns is_stale=False."""
    client._token_cache = {
        "token": MOCK_TOKEN,
        "expires_at": datetime.utcnow() + timedelta(hours=6),
    }
    mock_data = [{"id": 1, "name": "Pedestal A"}]

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.request = AsyncMock(return_value=MagicMock(
            status_code=200,
            json=lambda: mock_data,
            raise_for_status=lambda: None,
        ))
        mock_cls.return_value = mock_http

        data, is_stale = await client.list_pedestals(marina_id=1, db=mock_db)

    assert is_stale is False
    assert data == mock_data


# ─── StaleResponse dataclass ──────────────────────────────────────────────────

def test_stale_response_defaults():
    """StaleResponse with no cache has is_stale=True and last_synced_at=None."""
    sr = StaleResponse(data=None, is_stale=True)
    assert sr.is_stale is True
    assert sr.last_synced_at is None


def test_stale_response_with_data():
    """StaleResponse can hold data and a last_synced_at timestamp."""
    ts = datetime.utcnow()
    sr = StaleResponse(data={"pedestals": []}, is_stale=False, last_synced_at=ts)
    assert sr.is_stale is False
    assert sr.last_synced_at == ts
    assert sr.data == {"pedestals": []}


# ─── Factory tests ────────────────────────────────────────────────────────────

def test_factory_returns_same_instance_for_same_marina():
    """Factory caches and returns the same PedestalAPIClient for the same marina_id."""
    from app.services.pedestal_api_factory import PedestalAPIClientFactory
    from app.utils.encryption import encrypt_password

    factory = PedestalAPIClientFactory()

    mock_marina = MagicMock()
    mock_marina.id = 42
    mock_marina.pedestal_api_base_url = "http://test.pedestal"
    mock_marina.pedestal_service_email = "svc@test.local"
    mock_marina.pedestal_service_password_encrypted = encrypt_password("secret123")

    db = MagicMock()
    db.get.return_value = mock_marina

    client1 = factory.get_client(42, db)
    client2 = factory.get_client(42, db)

    assert client1 is client2


def test_factory_creates_new_client_on_credential_change():
    """Factory creates a fresh client when credentials change."""
    from app.services.pedestal_api_factory import PedestalAPIClientFactory
    from app.utils.encryption import encrypt_password

    factory = PedestalAPIClientFactory()

    mock_marina = MagicMock()
    mock_marina.id = 43
    mock_marina.pedestal_api_base_url = "http://test.pedestal"
    mock_marina.pedestal_service_email = "svc@test.local"
    mock_marina.pedestal_service_password_encrypted = encrypt_password("secret123")

    db = MagicMock()
    db.get.return_value = mock_marina

    client1 = factory.get_client(43, db)

    # Now simulate email change
    mock_marina.pedestal_service_email = "new-svc@test.local"
    mock_marina.pedestal_service_password_encrypted = encrypt_password("new-secret456")

    client2 = factory.get_client(43, db)

    assert client1 is not client2


def test_factory_raises_on_missing_credentials():
    """Factory raises ValueError when service credentials are not configured."""
    from app.services.pedestal_api_factory import PedestalAPIClientFactory

    factory = PedestalAPIClientFactory()

    mock_marina = MagicMock()
    mock_marina.id = 99
    mock_marina.pedestal_api_base_url = "http://test.pedestal"
    mock_marina.pedestal_service_email = None  # missing
    mock_marina.pedestal_service_password_encrypted = None

    db = MagicMock()
    db.get.return_value = mock_marina

    with pytest.raises(ValueError, match="pedestal_service_email"):
        factory.get_client(99, db)
