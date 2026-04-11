"""
PedestalAPIClient — JWT-authenticated async client for Pedestal SW External API.

Auth flow:
  1. POST {base_url}/api/auth/service-token with service account credentials
  2. Cache the JWT token with expiry (refreshes 60 s before expiry)
  3. All requests: Authorization: Bearer {token}, path prefix /api/ext/

Resilience:
  - 3 retries with exponential backoff (1s, 2s, 4s) on connect errors or 5xx
  - Falls back to pedestal_cache on all failures
  - Logs every request to sync_log

Token lifetime: Pedestal SW issues 8-hour JWTs (jwt_expire_minutes=480).
We cache for 7 hours (25 200 s) to ensure we refresh 1 hour before expiry.
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from ..models.cache import PedestalCache, SyncLog

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAYS = [1.0, 2.0, 4.0]   # seconds
_DEFAULT_TIMEOUT = 10.0
_TOKEN_CACHE_SECONDS = 7 * 3600    # 7 hours (JWT valid for 8 h; refresh 1 h early)


# ─── Custom exceptions ────────────────────────────────────────────────────────

class PedestalAuthError(Exception):
    """Raised when authentication to the Pedestal SW fails."""

    def __init__(self, marina_id: int, detail: str):
        super().__init__(detail)
        self.marina_id = marina_id
        self.detail = detail

    def __str__(self) -> str:
        return f"PedestalAuthError(marina_id={self.marina_id}): {self.detail}"


# ─── Return type ─────────────────────────────────────────────────────────────

@dataclass
class StaleResponse:
    """Wraps an API response to indicate whether it came from live or stale cache."""
    data: Any
    is_stale: bool
    last_synced_at: Optional[datetime] = field(default=None)


# ─── Client ───────────────────────────────────────────────────────────────────

class PedestalAPIClient:
    """
    JWT-authenticated async HTTP client for one marina's Pedestal SW instance.

    Token management:
    - Calls POST /api/auth/service-token on first use or after expiry.
    - Caches the token for _TOKEN_CACHE_SECONDS (7 h).
    - Thread-safe for asyncio (single event loop per FastAPI worker).

    All public methods return Tuple[Any, bool] for backwards compatibility
    with routers that unpack (data, is_stale).
    """

    def __init__(
        self,
        marina_id: int,
        base_url: str,
        service_email: str,
        service_password: str,
        timeout: float = _DEFAULT_TIMEOUT,
    ):
        self.marina_id = marina_id
        self.base_url = base_url.rstrip("/")
        self._service_email = service_email
        self._service_password = service_password
        self.timeout = timeout

        # Token cache: {'token': str, 'expires_at': datetime}
        self._token_cache: dict = {}

    # ─── Auth ─────────────────────────────────────────────────────────────────

    async def _get_token(self) -> str:
        """Return a valid JWT, logging in (and caching) if necessary."""
        now = datetime.utcnow()
        cached_token = self._token_cache.get("token")
        expires_at = self._token_cache.get("expires_at")

        if cached_token and expires_at and now < expires_at:
            return cached_token

        # Need to (re)authenticate
        login_url = f"{self.base_url}/api/auth/service-token"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    login_url,
                    json={"email": self._service_email, "password": self._service_password},
                    headers={"Accept": "application/json"},
                )
                if resp.status_code == 401 or resp.status_code == 403:
                    raise PedestalAuthError(
                        self.marina_id,
                        f"Login failed (HTTP {resp.status_code}): {resp.text[:200]}",
                    )
                resp.raise_for_status()
                body = resp.json()
        except PedestalAuthError:
            raise
        except httpx.HTTPStatusError as exc:
            raise PedestalAuthError(
                self.marina_id,
                f"Login HTTP error {exc.response.status_code}: {exc.response.text[:200]}",
            ) from exc
        except Exception as exc:
            raise PedestalAuthError(
                self.marina_id, f"Login request failed: {exc}"
            ) from exc

        token = body.get("access_token")
        if not token:
            raise PedestalAuthError(
                self.marina_id,
                f"Login response missing access_token: {json.dumps(body)[:200]}",
            )

        self._token_cache = {
            "token": token,
            "expires_at": now + timedelta(seconds=_TOKEN_CACHE_SECONDS),
        }
        logger.info(f"[PedestalAPI] Authenticated for marina {self.marina_id}")
        return token

    # ─── Core request ─────────────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        marina_id: int,
        db: Optional[Session],
        sync_type: str,
        body: Any = None,
        params: Optional[dict] = None,
    ) -> Tuple[Any, bool]:
        """
        Make an authenticated HTTP request with retry + exponential backoff.

        - Prefixes path with /api/ext/ if not already present.
        - On 5xx or connect error: retries up to _MAX_RETRIES times.
        - On all failures: returns cached stale data or (None, True).
        - Writes to sync_log on success, error, and stale.
        """
        # Ensure path uses /api/ext/ prefix
        if not path.startswith("/api/ext/"):
            path = "/api/ext/" + path.lstrip("/")

        url = f"{self.base_url}{path}"
        started_at = datetime.utcnow()
        last_error: Optional[str] = None

        for attempt in range(_MAX_RETRIES):
            try:
                token = await self._get_token()
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                }
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    kwargs: dict = {"headers": headers}
                    if params:
                        kwargs["params"] = params
                    if body is not None:
                        kwargs["json"] = body
                    resp = await client.request(method, url, **kwargs)
                    resp.raise_for_status()
                    data = resp.json()

                completed_at = datetime.utcnow()
                _write_sync_log(db, marina_id, sync_type, "success", started_at, completed_at)
                return data, False

            except PedestalAuthError:
                # Auth failures should not be retried
                last_error = f"Authentication failed for marina {marina_id}"
                logger.error(f"[PedestalAPI] {last_error}")
                break

            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    f"[PedestalAPI] {sync_type} attempt {attempt + 1}/{_MAX_RETRIES} "
                    f"failed for marina {marina_id}: {last_error}"
                )
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_RETRY_DELAYS[attempt])

            except httpx.HTTPStatusError as exc:
                last_error = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
                logger.error(
                    f"[PedestalAPI] {sync_type} HTTP error for marina {marina_id}: {last_error}"
                )
                # Invalidate token cache on 401 so next attempt re-authenticates
                if exc.response.status_code == 401:
                    self._token_cache = {}
                # Don't retry on 4xx client errors
                if exc.response.status_code < 500:
                    break
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_RETRY_DELAYS[attempt])

            except Exception as exc:
                last_error = str(exc)
                logger.error(f"[PedestalAPI] {sync_type} unexpected error: {last_error}")
                break

        # All retries exhausted — fall back to stale cache
        completed_at = datetime.utcnow()
        _write_sync_log(db, marina_id, sync_type, "error", started_at, completed_at, last_error)

        cached = _get_cache(db, marina_id, sync_type)
        if cached is not None:
            logger.info(f"[PedestalAPI] {sync_type} using stale cache for marina {marina_id}")
            _write_sync_log(db, marina_id, sync_type, "stale", started_at, completed_at)
            return cached, True

        return None, True

    async def _get(
        self,
        path: str,
        marina_id: int,
        db: Optional[Session],
        sync_type: str,
        cache_key: Optional[str] = None,
        params: Optional[dict] = None,
    ) -> Tuple[Any, bool]:
        """GET with cache write on success."""
        data, is_stale = await self._request(
            "GET", path, marina_id, db, sync_type, params=params
        )
        if not is_stale and data is not None and db is not None:
            _update_cache(db, marina_id, cache_key or sync_type, data)
        return data, is_stale

    # ─── Public API methods ───────────────────────────────────────────────────

    async def list_pedestals(self, marina_id: int, db: Session) -> Tuple[Any, bool]:
        return await self._get("/api/ext/pedestals", marina_id, db, "list_pedestals")

    async def get_health(self, marina_id: int, db: Session) -> Tuple[Any, bool]:
        return await self._get("/api/ext/pedestals/health", marina_id, db, "get_health")

    async def get_active_sessions(self, marina_id: int, db: Session) -> Tuple[Any, bool]:
        return await self._get("/api/ext/sessions/active", marina_id, db, "get_active_sessions")

    async def get_pending_sessions(self, marina_id: int, db: Session) -> Tuple[Any, bool]:
        return await self._get("/api/ext/sessions/pending", marina_id, db, "get_pending_sessions")

    async def allow_session(self, session_id: int) -> dict:
        """Allow a pending session — no caching, direct action."""
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/ext/controls/{session_id}/allow",
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def deny_session(self, session_id: int, reason: Optional[str] = None) -> dict:
        """Deny a pending session."""
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        payload = {"reason": reason} if reason else {}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/ext/controls/{session_id}/deny",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def stop_session(self, session_id: int) -> dict:
        """Stop an active session."""
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/ext/controls/{session_id}/stop",
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_daily_analytics(
        self,
        marina_id: int,
        db: Session,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Tuple[Any, bool]:
        params: dict = {}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        return await self._get(
            "/api/ext/analytics/consumption/daily",
            marina_id,
            db,
            "get_daily_analytics",
            params=params,
        )

    async def get_session_summary(self, marina_id: int, db: Session) -> Tuple[Any, bool]:
        return await self._get(
            "/api/ext/analytics/sessions/summary", marina_id, db, "get_session_summary"
        )

    async def get_active_alarms(self, marina_id: int, db: Session) -> Tuple[Any, bool]:
        return await self._get("/api/ext/alarms/active", marina_id, db, "get_active_alarms")

    async def acknowledge_alarm(self, alarm_id: int) -> dict:
        """Acknowledge an alarm on the Pedestal SW."""
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/ext/alarms/{alarm_id}/acknowledge",
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def list_berths(self, marina_id: int, db: Session) -> Tuple[Any, bool]:
        return await self._get("/api/ext/berths", marina_id, db, "list_berths")

    async def run_diagnostics(self, pedestal_id: int) -> dict:
        """Run diagnostics on a specific pedestal — no caching."""
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/ext/pedestals/{pedestal_id}/diagnostics/run",
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_camera_detections(self, pedestal_id: int) -> dict:
        """Get latest camera detections for a pedestal."""
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.base_url}/api/ext/camera/{pedestal_id}/detections",
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_berth_occupancy(
        self, pedestal_id: int, marina_id: int, db: Optional[Session]
    ) -> Tuple[Any, bool]:
        """
        GET /api/ext/pedestals/{pedestal_id}/berths/occupancy.
        Returns per-pedestal berth occupancy list from the Pedestal SW.
        Cached per pedestal_id; falls back to stale cache on failure.
        """
        return await self._get(
            f"/api/ext/pedestals/{pedestal_id}/berths/occupancy",
            marina_id,
            db,
            f"berth_occupancy_{pedestal_id}",
        )

    async def get_camera_frame(
        self, pedestal_id: int, marina_id: int, db: Optional[Session] = None
    ) -> bytes:
        """
        GET /api/ext/pedestals/{pedestal_id}/camera/frame.
        Returns raw JPEG bytes.  No stale-cache (bytes cannot be stored in the
        JSON PedestalCache column).  Retries up to _MAX_RETRIES times and writes
        to sync_log on success and failure; raises on all retry exhaustion.
        """
        url = f"{self.base_url}/api/ext/pedestals/{pedestal_id}/camera/frame"
        sync_type = f"camera_frame_{pedestal_id}"
        started_at = datetime.utcnow()
        last_error: Optional[str] = None

        for attempt in range(_MAX_RETRIES):
            try:
                token = await self._get_token()
                headers = {"Authorization": f"Bearer {token}", "Accept": "image/jpeg,*/*"}
                async with httpx.AsyncClient(timeout=self.timeout) as http_client:
                    resp = await http_client.get(url, headers=headers)
                    resp.raise_for_status()
                    frame_bytes = resp.content

                completed_at = datetime.utcnow()
                _write_sync_log(db, marina_id, sync_type, "success", started_at, completed_at)
                return frame_bytes

            except PedestalAuthError:
                raise

            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    f"[PedestalAPI] {sync_type} attempt {attempt + 1}/{_MAX_RETRIES}: {last_error}"
                )
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_RETRY_DELAYS[attempt])

            except httpx.HTTPStatusError as exc:
                last_error = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
                logger.error(f"[PedestalAPI] {sync_type} HTTP error: {last_error}")
                if exc.response.status_code == 401:
                    self._token_cache = {}
                if exc.response.status_code < 500:
                    break
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_RETRY_DELAYS[attempt])

            except Exception as exc:
                last_error = str(exc)
                logger.error(f"[PedestalAPI] {sync_type} unexpected error: {last_error}")
                break

        completed_at = datetime.utcnow()
        _write_sync_log(
            db, marina_id, sync_type, "error", started_at, completed_at, last_error
        )
        raise httpx.RequestError(
            f"Camera frame unavailable for pedestal {pedestal_id}: {last_error or 'Unknown error'}"
        )

    async def get_camera_stream_url(
        self, pedestal_id: int, marina_id: int, db: Optional[Session]
    ) -> Tuple[Any, bool]:
        """
        GET /api/ext/pedestals/{pedestal_id}/camera/stream.
        Returns RTSP stream URL + reachability from the Pedestal SW.
        Cached per pedestal_id; falls back to stale cache on failure.
        """
        return await self._get(
            f"/api/ext/pedestals/{pedestal_id}/camera/stream",
            marina_id,
            db,
            f"camera_stream_{pedestal_id}",
        )


# ─── Backwards-compat alias ───────────────────────────────────────────────────
# Routers that still reference PedestalAPIService will continue to work while
# we migrate them to use the factory.
PedestalAPIService = PedestalAPIClient


# ─── Cache helpers ────────────────────────────────────────────────────────────

def _update_cache(
    db: Optional[Session], marina_id: int, cache_key: str, data: Any
) -> None:
    if db is None:
        return
    try:
        cache_id = abs(hash(cache_key)) % (10**9)
        entry = (
            db.query(PedestalCache)
            .filter(
                PedestalCache.marina_id == marina_id,
                PedestalCache.pedestal_id == cache_id,
            )
            .first()
        )
        if entry:
            entry.last_seen_data = data
            entry.last_synced_at = datetime.utcnow()
            entry.is_stale = False
        else:
            entry = PedestalCache(
                marina_id=marina_id,
                pedestal_id=cache_id,
                last_seen_data=data,
                last_synced_at=datetime.utcnow(),
                is_stale=False,
            )
            db.add(entry)
        db.commit()
    except Exception as exc:
        logger.warning(f"Cache update failed: {exc}")
        try:
            db.rollback()
        except Exception:
            pass


def _get_cache(
    db: Optional[Session], marina_id: int, cache_key: str
) -> Optional[Any]:
    if db is None:
        return None
    try:
        cache_id = abs(hash(cache_key)) % (10**9)
        entry = (
            db.query(PedestalCache)
            .filter(
                PedestalCache.marina_id == marina_id,
                PedestalCache.pedestal_id == cache_id,
            )
            .first()
        )
        if entry and entry.last_seen_data is not None:
            entry.is_stale = True
            db.commit()
            return entry.last_seen_data
        return None
    except Exception:
        return None


def _write_sync_log(
    db: Optional[Session],
    marina_id: int,
    sync_type: str,
    status: str,
    started_at: datetime,
    completed_at: datetime,
    error_message: Optional[str] = None,
) -> None:
    if db is None:
        return
    try:
        entry = SyncLog(
            marina_id=marina_id,
            sync_type=sync_type,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            error_message=error_message,
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        logger.warning(f"sync_log write failed: {exc}")
        try:
            db.rollback()
        except Exception:
            pass
