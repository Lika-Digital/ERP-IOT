"""
PedestalAPIService — async HTTP client for Pedestal SW REST APIs.

Design principles:
- Each method passes X-API-Key header
- Up to 3 retries with exponential backoff (1s, 2s, 4s)
- Logs duration + status to sync_log table
- Returns (data, is_stale) tuple — is_stale=True when using cached data
- Cache stored in pedestal_cache table per (marina_id, pedestal_id)
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from ..models.cache import PedestalCache, SyncLog

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAYS = [1.0, 2.0, 4.0]  # seconds
_DEFAULT_TIMEOUT = 10.0


class PedestalAPIService:
    def __init__(self, base_url: str, api_key: str, timeout: float = _DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._headers = {"X-API-Key": api_key, "Accept": "application/json"}

    # ─── Private helpers ─────────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        marina_id: int,
        db: Optional[Session],
        sync_type: str,
        **kwargs,
    ) -> Tuple[Any, bool]:
        """
        Make an HTTP request with retry + exponential backoff.
        Returns (data, is_stale).
        """
        url = f"{self.base_url}{path}"
        started_at = datetime.utcnow()
        last_error: Optional[str] = None

        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout, headers=self._headers
                ) as client:
                    resp = await client.request(method, url, **kwargs)
                    resp.raise_for_status()
                    data = resp.json()

                completed_at = datetime.utcnow()
                _write_sync_log(
                    db, marina_id, sync_type, "success", started_at, completed_at
                )
                return data, False

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
                # Don't retry on 4xx (bad request / unauthorized)
                if exc.response.status_code < 500:
                    break
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_RETRY_DELAYS[attempt])

            except Exception as exc:
                last_error = str(exc)
                logger.error(f"[PedestalAPI] {sync_type} unexpected error: {last_error}")
                break

        # All retries exhausted — return cached stale data if available
        completed_at = datetime.utcnow()
        _write_sync_log(
            db, marina_id, sync_type, "error", started_at, completed_at, last_error
        )

        cached = _get_cache(db, marina_id, sync_type)
        if cached is not None:
            logger.info(
                f"[PedestalAPI] {sync_type} using stale cache for marina {marina_id}"
            )
            _write_sync_log(
                db, marina_id, sync_type, "stale", started_at, completed_at
            )
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
        """GET with optional cache write on success."""
        data, is_stale = await self._request(
            "GET", path, marina_id, db, sync_type, params=params
        )
        if not is_stale and data is not None and db is not None:
            _update_cache(db, marina_id, cache_key or sync_type, data)
        return data, is_stale

    # ─── Public API methods ───────────────────────────────────────────────────

    async def list_pedestals(self, marina_id: int, db: Session) -> Tuple[Any, bool]:
        return await self._get(
            "/api/pedestals", marina_id, db, "list_pedestals"
        )

    async def get_health(self, marina_id: int, db: Session) -> Tuple[Any, bool]:
        return await self._get(
            "/api/pedestals/health", marina_id, db, "get_health"
        )

    async def get_active_sessions(self, marina_id: int, db: Session) -> Tuple[Any, bool]:
        return await self._get(
            "/api/sessions/active", marina_id, db, "get_active_sessions"
        )

    async def get_pending_sessions(self, marina_id: int, db: Session) -> Tuple[Any, bool]:
        return await self._get(
            "/api/sessions/pending", marina_id, db, "get_pending_sessions"
        )

    async def allow_session(self, session_id: int) -> dict:
        """Allow a pending session — no caching, direct action."""
        async with httpx.AsyncClient(
            timeout=self.timeout, headers=self._headers
        ) as client:
            resp = await client.post(f"{self.base_url}/api/controls/{session_id}/allow")
            resp.raise_for_status()
            return resp.json()

    async def deny_session(self, session_id: int, reason: Optional[str] = None) -> dict:
        """Deny a pending session."""
        async with httpx.AsyncClient(
            timeout=self.timeout, headers=self._headers
        ) as client:
            payload = {"reason": reason} if reason else {}
            resp = await client.post(
                f"{self.base_url}/api/controls/{session_id}/deny", json=payload
            )
            resp.raise_for_status()
            return resp.json()

    async def stop_session(self, session_id: int) -> dict:
        """Stop an active session."""
        async with httpx.AsyncClient(
            timeout=self.timeout, headers=self._headers
        ) as client:
            resp = await client.post(f"{self.base_url}/api/controls/{session_id}/stop")
            resp.raise_for_status()
            return resp.json()

    async def get_daily_analytics(
        self,
        marina_id: int,
        db: Session,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Tuple[Any, bool]:
        params = {}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        return await self._get(
            "/api/analytics/consumption/daily",
            marina_id,
            db,
            "get_daily_analytics",
            params=params,
        )

    async def get_session_summary(self, marina_id: int, db: Session) -> Tuple[Any, bool]:
        return await self._get(
            "/api/analytics/sessions/summary", marina_id, db, "get_session_summary"
        )

    async def get_active_alarms(self, marina_id: int, db: Session) -> Tuple[Any, bool]:
        return await self._get(
            "/api/alarms/active", marina_id, db, "get_active_alarms"
        )

    async def acknowledge_alarm(self, alarm_id: int) -> dict:
        """Acknowledge an alarm on the Pedestal SW."""
        async with httpx.AsyncClient(
            timeout=self.timeout, headers=self._headers
        ) as client:
            resp = await client.post(f"{self.base_url}/api/alarms/{alarm_id}/acknowledge")
            resp.raise_for_status()
            return resp.json()

    async def list_berths(self, marina_id: int, db: Session) -> Tuple[Any, bool]:
        return await self._get(
            "/api/berths", marina_id, db, "list_berths"
        )

    async def run_diagnostics(self, pedestal_id: int) -> dict:
        """Run diagnostics on a specific pedestal — no caching."""
        async with httpx.AsyncClient(
            timeout=self.timeout, headers=self._headers
        ) as client:
            resp = await client.post(
                f"{self.base_url}/api/pedestals/{pedestal_id}/diagnostics/run"
            )
            resp.raise_for_status()
            return resp.json()

    async def get_camera_detections(self, pedestal_id: int) -> dict:
        """Get latest camera detections for a pedestal."""
        async with httpx.AsyncClient(
            timeout=self.timeout, headers=self._headers
        ) as client:
            resp = await client.get(
                f"{self.base_url}/api/camera/{pedestal_id}/detections"
            )
            resp.raise_for_status()
            return resp.json()


# ─── Cache helpers ────────────────────────────────────────────────────────────

def _update_cache(
    db: Optional[Session], marina_id: int, cache_key: str, data: Any
) -> None:
    if db is None:
        return
    try:
        # Use cache_key as a pseudo pedestal_id=-1 keyed by sync_type string
        # For per-pedestal caching the caller passes the real pedestal_id
        cache_id = abs(hash(cache_key)) % (10**9)  # stable int from string
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
            # Mark as stale
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
