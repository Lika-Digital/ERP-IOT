"""Cabinet client — channel A (Bearer, /api/ext) and channel B (X-API-Key, /api/nfc).

Response handling is the table in spec §2.5, in one place:

  401  first time: drop the cached token, ONE retry; second time: cabinet_auth_failed,
       full URL in the log (a doubled /api/ext/ext/ also answers 401, NALAZ 1.2)
  403  not_enabled: no retry, the key is not called again for an hour
  503  {"reason": "Not enabled"} on direct routes -> not_enabled (same as 403 on the
       gateway: the operator did not enable it); any other 503 -> capability_unavailable
  409  by the cabinet's exact text: standalone | awaiting_plug | outlet_busy |
       already_ended | nfc_mapping_mismatch | conflict
  400  session_state_changed or erp_bug
  404  not_found
  422  erp_bug — logged as a bug, never retried
  5xx / timeout / connect: 3 attempts (waits 1 s, 2 s), then the cache with
       is_stale=True, or no_contact when there is no cache

The cache is keyed by endpoint key AND its parameters (spec §11 O20): a daily
analytics read for one date range never falls back to another range's data.
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

import certifi
import httpx
from jose import jwt
from sqlalchemy.orm import Session

from ..utils.time import utcnow
from . import contract
from .outcomes import Outcome, classify_400, classify_409

# ONE TLS context for the process. httpx builds a fresh one for every client it
# creates, re-reading the CA bundle: ~0.24 s of CPU, on the event loop, per call.
# With a client per call that was 2-3 s of a berths request and, on a busy
# machine, more than 10 (spec §11 O61). Verification is unchanged: certifi's CAs.
TLS = ssl.create_default_context(cafile=certifi.where())

logger = logging.getLogger(__name__)

ATTEMPTS = 3
BACKOFF = (1.0, 2.0)                 # waits between the 3 attempts
DEFAULT_TIMEOUT = 10.0
NOT_ENABLED_RETRY = timedelta(hours=1)
# The cabinet's token lives 120 min (Cloud_IOT config.py:21) and its response
# has no expires_in. We read `exp` from the JWT; if we cannot, assume this.
FALLBACK_TOKEN_LIFETIME = timedelta(minutes=100)
TOKEN_MARGIN = timedelta(minutes=5)


def cache_key(endpoint_key: str, path: str, query: Optional[dict]) -> str:
    q = "&".join(f"{k}={query[k]}" for k in sorted(query or {}) if query[k] is not None)
    return f"{endpoint_key}:{path}" + (f"?{q}" if q else "")


class CabinetClient:
    def __init__(
        self,
        marina_id: int,
        base_url: str,
        service_email: str,
        service_password: str,
        erp_api_key: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.marina_id = marina_id
        self.base_url = base_url.rstrip("/")
        self._service_email = service_email
        self._service_password = service_password
        self._erp_api_key = erp_api_key
        self.timeout = timeout
        self._transport = transport
        self._sleep = sleep
        self._token: Optional[str] = None
        self._token_expires: Optional[datetime] = None
        self._not_enabled_until: dict[str, datetime] = {}
        # sync_log records CHANGES, not a heartbeat (phase 4): with the collector polling,
        # a row per successful call was 10 400 rows a day of "success" for two cabinets
        self._last_status: dict[str, str] = {}

    # ── plumbing ─────────────────────────────────────────────────────────────

    def _http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout, transport=self._transport, verify=TLS)

    def _drop_token(self) -> None:
        self._token = None
        self._token_expires = None

    async def _token_now(self) -> Optional[str]:
        now = utcnow()
        if self._token and self._token_expires and now < self._token_expires:
            return self._token
        async with self._http() as http:
            resp = await http.post(
                f"{self.base_url}/api/auth/service-token",
                json={"email": self._service_email, "password": self._service_password},
                headers={"Accept": "application/json"},
            )
        if resp.status_code != 200:
            logger.error("[cabinet] marina=%s service-token refused: HTTP %s %s",
                         self.marina_id, resp.status_code, resp.text[:200])
            return None
        token = resp.json().get("access_token")
        if not token:
            return None
        exp = _jwt_exp(token)
        expires = (exp - TOKEN_MARGIN) if exp else now + FALLBACK_TOKEN_LIFETIME
        self._token, self._token_expires = token, expires
        return token

    def url_for(self, key: str, **path_params) -> str:
        """The full URL a call would use — for command_audit, written before the call.
        A path the contract refuses is recorded as such (the call itself will not go)."""
        try:
            return f"{self.base_url}{contract.build_path(key, **path_params)}"
        except contract.ContractError as exc:
            return f"{self.base_url} <not sent: {exc}>"

    def is_known_not_enabled(self, key: str) -> bool:
        until = self._not_enabled_until.get(key)
        return bool(until and utcnow() < until)

    # ── channel A ────────────────────────────────────────────────────────────

    async def call(
        self,
        key: str,
        *,
        path_params: Optional[dict] = None,
        query: Optional[dict] = None,
        body: Any = None,
        db: Optional[Session] = None,
    ) -> Outcome:
        try:
            path = contract.build_path(key, **(path_params or {}))
        except contract.ContractError as exc:
            logger.error("[cabinet] ERP BUG, not sent: %s", exc)
            return Outcome("erp_bug", key, cabinet_detail=str(exc))

        method = contract.ENDPOINTS[key].method
        until = self._not_enabled_until.get(key)
        if until and utcnow() < until:
            return Outcome("not_enabled", key)

        url = f"{self.base_url}{path}"
        # per cabinet SERVER: a marina may have several (D28), and the same path on two
        # of them (pedestals.health, berths.list, .../pedestals/1/...) is not one fact
        ckey = f"{cache_key(key, path, query)}@{self.base_url}"
        started = utcnow()
        last_error = None
        retried_auth = False
        attempt = 0

        while attempt < ATTEMPTS:
            try:
                token = await self._token_now()
                if token is None:
                    self._last_status[key] = "error"
                    _sync_log(db, self.marina_id, key, "error", started, "service-token refused")
                    return Outcome("cabinet_auth_failed", key, http_status=401)
                async with self._http() as http:
                    resp = await http.request(
                        method, url,
                        headers={"Authorization": f"Bearer {token}",
                                 "Accept": "application/json"},
                        params={k: v for k, v in (query or {}).items() if v is not None} or None,
                        json=body if body is not None else None,
                    )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                attempt += 1
                if attempt < ATTEMPTS:
                    await self._sleep(BACKOFF[attempt - 1])
                continue

            status = resp.status_code
            if 200 <= status < 300:
                data = _json_or_bytes(resp)
                if self._last_status.get(key) != "success":
                    _sync_log(db, self.marina_id, key, "success", started)   # first, or recovered
                self._last_status[key] = "success"
                if method == "GET" and db is not None and not isinstance(data, bytes):
                    _cache_put(db, self.marina_id, ckey, data)
                return Outcome("ok", key, data=data, http_status=status)

            detail = _detail(resp)
            if status == 401:
                if not retried_auth:
                    retried_auth = True
                    self._drop_token()
                    continue          # one re-login, does not count as an attempt
                logger.error("[cabinet] 401 twice for %s %s — wrong service account, or a "
                             "malformed path (doubled ext?)", method, url)
                self._last_status[key] = "error"
                _sync_log(db, self.marina_id, key, "error", started, f"401 {detail}")
                return Outcome("cabinet_auth_failed", key, http_status=401, cabinet_detail=detail)
            if status == 403:
                self._not_enabled_until[key] = utcnow() + NOT_ENABLED_RETRY
                self._last_status[key] = "error"
                _sync_log(db, self.marina_id, key, "error", started, f"403 {detail}")
                return Outcome("not_enabled", key, http_status=403, cabinet_detail=detail)
            if status == 503:
                body_json = _safe_json(resp)
                if isinstance(body_json, dict) and body_json.get("reason") == "Not enabled":
                    self._not_enabled_until[key] = utcnow() + NOT_ENABLED_RETRY
                    return Outcome("not_enabled", key, http_status=503, cabinet_detail=detail)
                return Outcome("capability_unavailable", key, http_status=503,
                               cabinet_detail=detail)
            if status == 409:
                return Outcome(classify_409(detail), key, http_status=409, cabinet_detail=detail)
            if status == 400:
                code = classify_400(detail)
                if code == "erp_bug":
                    logger.error("[cabinet] ERP BUG: 400 from %s %s: %s", method, url, detail)
                return Outcome(code, key, http_status=400, cabinet_detail=detail)
            if status == 404:
                return Outcome("not_found", key, http_status=404, cabinet_detail=detail)
            if status == 422:
                logger.error("[cabinet] ERP BUG: 422 from %s %s: %s", method, url, detail)
                self._last_status[key] = "error"
                _sync_log(db, self.marina_id, key, "error", started, f"422 {detail}")
                return Outcome("erp_bug", key, http_status=422, cabinet_detail=detail)
            if status >= 500:
                last_error = f"HTTP {status}: {detail}"
                attempt += 1
                if attempt < ATTEMPTS:
                    await self._sleep(BACKOFF[attempt - 1])
                continue
            logger.error("[cabinet] unexpected HTTP %s from %s %s: %s", status, method, url, detail)
            return Outcome("erp_bug", key, http_status=status, cabinet_detail=detail)

        self._last_status[key] = "error"
        _sync_log(db, self.marina_id, key, "error", started, last_error)
        if method == "GET":
            cached = _cache_get(db, self.marina_id, ckey)
            if cached is not None:
                data, synced = cached
                self._last_status[key] = "stale"
                _sync_log(db, self.marina_id, key, "stale", started)
                return Outcome("stale", key, data=data, is_stale=True, synced_at=synced,
                               cabinet_detail=last_error)
        return Outcome("no_contact", key, is_stale=True, cabinet_detail=last_error)

    # ── channel B — NFC, X-API-Key, direct (§2.4) ────────────────────────────

    @property
    def has_channel_b(self) -> bool:
        return bool(self._erp_api_key)

    async def _nfc(self, method: str, path: str, key: str, *, body=None, query=None) -> Outcome:
        if not self._erp_api_key:
            return Outcome("capability_unavailable", key, cabinet_detail="no X-API-Key configured")
        url = f"{self.base_url}{path}"
        last_error = None
        for attempt in range(ATTEMPTS):
            try:
                async with self._http() as http:
                    # never a Bearer header here: the cabinet would validate it as a
                    # customer token and refuse (customer_dependencies.py:12-47)
                    resp = await http.request(method, url, json=body, params=query,
                                              headers={"X-API-Key": self._erp_api_key,
                                                       "Accept": "application/json"})
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = str(exc)
                if attempt < ATTEMPTS - 1:
                    await self._sleep(BACKOFF[attempt])
                continue
            s, detail = resp.status_code, _detail(resp)
            if 200 <= s < 300:
                return Outcome("ok", key, data=resp.json(), http_status=s)
            if s == 401:
                logger.error("[cabinet] channel B refused X-API-Key for %s %s", method, url)
                return Outcome("cabinet_auth_failed", key, http_status=401, cabinet_detail=detail)
            if s == 409:
                return Outcome(classify_409(detail), key, http_status=409, cabinet_detail=detail)
            if s == 404:
                return Outcome("not_found", key, http_status=404, cabinet_detail=detail)
            if s == 503:
                return Outcome("capability_unavailable", key, http_status=503,
                               cabinet_detail=detail)
            if s >= 500:
                last_error = f"HTTP {s}: {detail}"
                if attempt < ATTEMPTS - 1:
                    await self._sleep(BACKOFF[attempt])
                continue
            return Outcome("erp_bug", key, http_status=s, cabinet_detail=detail)
        return Outcome("no_contact", key, cabinet_detail=last_error)

    async def nfc_scan(self, nfc_tag_id: str, user_id: str) -> Outcome:
        return await self._nfc("POST", contract.NFC_SCAN, "nfc.scan",
                               body={"nfc_tag_id": nfc_tag_id, "user_id": user_id})

    async def nfc_stop(self, session_id: int) -> Outcome:
        """409 'already ended by operator' -> already_ended, which is not an error (D10)."""
        return await self._nfc("POST", contract.NFC_SESSION_STOP.format(session_id=session_id),
                               "nfc.stop")

    # Both reads below WRITE last_reconciled_at on the cabinet (nfc.py:688-759,
    # erp_reconciliation.py:112-124). Calling them for display would silence the
    # cabinet's "ERP is not reconciling" detector exactly when it should fire
    # (§7.2 R2). The names say what they are for; TC-ERP-SIM-00g enforces it.
    async def nfc_session_for_reconciliation(self, session_id: int) -> Outcome:
        return await self._nfc("GET", contract.NFC_SESSION.format(session_id=session_id),
                               "nfc.session")

    async def nfc_sessions_by_user_for_reconciliation(
        self, user_id: str, status: Optional[str] = None, limit: int = 100
    ) -> Outcome:
        return await self._nfc("GET", contract.NFC_SESSIONS_BY_USER.format(user_id=user_id),
                               "nfc.sessions_by_user",
                               query={k: v for k, v in (("status", status), ("limit", limit))
                                      if v is not None})

    async def nfc_sessions_ended_between(self, ended_from: datetime, ended_to: datetime,
                                         limit: int = 100, offset: int = 0) -> Outcome:
        """R14 b: sessions by END time, [ended_from, ended_to), one page. Read-only on
        the cabinet once b is in (that is the point of R14 (4))."""
        return await self._nfc("GET", contract.NFC_SESSIONS_RANGE, "nfc.sessions_range",
                               query={"ended_from": _iso_z(ended_from),
                                      "ended_to": _iso_z(ended_to),
                                      "limit": limit, "offset": offset})

    async def nfc_ack(self, cabinet_session_ids: list) -> Outcome:
        """R14 c: the ERP says, explicitly, which sessions it has reconciled."""
        return await self._nfc("POST", contract.NFC_SESSIONS_ACK, "nfc.ack",
                               body={"session_ids": list(cabinet_session_ids)})

    # ── named reads/commands used by routers ─────────────────────────────────

    async def health(self, db=None):
        return await self.call("pedestals.health", db=db)

    async def list_pedestals(self, db=None):
        return await self.call("pedestals.list", db=db)

    async def list_berths(self, db=None):
        return await self.call("berths.list", db=db)

    async def active_sessions(self, db=None):
        return await self.call("sessions.active", db=db)

    async def pending_sessions(self, db=None):
        return await self.call("sessions.pending", db=db)

    async def active_alarms(self, db=None):
        return await self.call("alarms.active", db=db)

    async def daily_analytics(self, db=None, date_from=None, date_to=None):
        return await self.call("analytics.daily", db=db,
                               query={"date_from": date_from, "date_to": date_to})

    async def session_summary(self, db=None):
        return await self.call("analytics.summary", db=db)

    async def pedestal_status(self, pedestal_ref, db=None):
        return await self.call("pedestals.status_ext", path_params={"pedestal_id": pedestal_ref},
                               db=db)

    async def pedestal_load(self, pedestal_pk: int, db=None):
        return await self.call("load.pedestal_get_ext", path_params={"pedestal_id": pedestal_pk},
                               db=db)

    async def pedestal_breakers(self, pedestal_pk: int, db=None):
        return await self.call("breakers.pedestal_list_ext",
                               path_params={"pedestal_id": pedestal_pk}, db=db)

    async def pedestal_load_alarms(self, pedestal_pk: int, db=None):
        return await self.call("load.pedestal_alarms_ext",
                               path_params={"pedestal_id": pedestal_pk}, db=db)

    async def berth_occupancy(self, pedestal_ref, db=None):
        return await self.call("berths.occupancy_ext", path_params={"pedestal_id": pedestal_ref},
                               db=db)

    async def camera_frame(self, pedestal_ref, db=None):
        return await self.call("camera.frame_ext", path_params={"pedestal_id": pedestal_ref},
                               db=db)

    async def camera_stream(self, pedestal_ref, db=None):
        return await self.call("camera.stream_ext", path_params={"pedestal_id": pedestal_ref},
                               db=db)

    async def allow_session(self, session_id: int, db=None):
        return await self.call("controls.allow", path_params={"session_id": session_id}, db=db)

    async def deny_session(self, session_id: int, reason: Optional[str] = None, db=None):
        return await self.call("controls.deny", path_params={"session_id": session_id},
                               body={"reason": reason} if reason else {}, db=db)

    async def stop_session(self, session_id: int, db=None):
        return await self.call("controls.stop", path_params={"session_id": session_id}, db=db)

    async def acknowledge_alarm(self, alarm_id: int, db=None):
        return await self.call("alarms.acknowledge", path_params={"alarm_id": alarm_id}, db=db)

    async def run_diagnostics(self, pedestal_pk: int, db=None):
        return await self.call("diagnostics.run", path_params={"pedestal_id": pedestal_pk}, db=db)

    async def socket_cmd(self, pedestal_pk: int, outlet: str, action: str,
                         nfc_tag_id: Optional[str] = None, db=None):
        body = {"action": action}
        if nfc_tag_id:
            body["nfc_tag_id"] = nfc_tag_id   # sent from phase 2 on (§2.3), ignored on Krk today
        key = "controls.socket_cmd" if outlet.startswith("Q") else "controls.water_cmd"
        name = "socket_name" if outlet.startswith("Q") else "valve_name"
        return await self.call(key, path_params={"pedestal_id": pedestal_pk, name: outlet},
                               body=body, db=db)


# ── helpers ───────────────────────────────────────────────────────────────────

def _jwt_exp(token: str) -> Optional[datetime]:
    """`exp` of the cabinet's JWT as naive UTC, or None for an opaque token."""
    try:
        exp = jwt.get_unverified_claims(token).get("exp")
    except Exception:  # noqa: BLE001 — not a JWT: the caller uses the fallback lifetime
        return None
    if not exp:
        return None
    return datetime.fromtimestamp(exp, timezone.utc).replace(tzinfo=None)


def _iso_z(dt: datetime) -> str:
    """Naive UTC -> the cabinet's ISO form with Z."""
    return dt.replace(microsecond=0).isoformat() + "Z"


def is_missing_route(outcome: Outcome) -> bool:
    """A 404 from FastAPI's router (the route does not exist), not a 404 from a handler
    ("Session not found"). That is how the ERP learns the cabinet has no R14 b/c yet."""
    return outcome.code == "not_found" and outcome.cabinet_detail == "Not Found"


def _safe_json(resp: httpx.Response):
    try:
        return resp.json()
    except (json.JSONDecodeError, ValueError):
        return None


def _detail(resp: httpx.Response) -> str:
    j = _safe_json(resp)
    if isinstance(j, dict):
        d = j.get("detail", j.get("reason", ""))
        return d if isinstance(d, str) else json.dumps(d)[:500]
    return resp.text[:500]


def _json_or_bytes(resp: httpx.Response):
    if resp.headers.get("content-type", "").startswith("application/json"):
        return resp.json()
    return resp.content


def _cache_put(db: Session, marina_id: int, key: str, data: Any) -> None:
    from ..services.pedestal_api import _update_cache
    _update_cache(db, marina_id, key, data)


def _cache_get(db: Optional[Session], marina_id: int, key: str):
    if db is None:
        return None
    from ..models.cache import PedestalCache
    try:
        row = (db.query(PedestalCache)
               .filter(PedestalCache.marina_id == marina_id, PedestalCache.cache_key == key)
               .first())
    except Exception:  # noqa: BLE001 — a broken cache is "no cache", never a crash
        return None
    if row is None or row.last_seen_data is None:
        return None
    return row.last_seen_data, row.last_synced_at


def _sync_log(db, marina_id, key, status, started, error=None) -> None:
    """Errors and stale answers: every time. Success: only the first after a non-success
    (the caller decides) — when it broke and when it came back, not every poll."""
    from ..services.pedestal_api import _write_sync_log
    _write_sync_log(db, marina_id, key, status, started, utcnow(), error)
