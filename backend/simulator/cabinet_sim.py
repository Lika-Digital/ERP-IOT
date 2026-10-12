"""Simulator of the marina cabinet API, built from the cabinet's CODE (spec §9.1).

Source: Cloud_IOT at commit a709cf8 (branch develop), read with `git show` only.
Every body, status code and `detail` string below is taken from that code; the
references are kept next to each handler so a divergence can be checked
against one line. There are no recorded Krk responses in this repo; where the
spec says "built from recorded responses", this is built from the code that
produces them, and TC-ERP-LIVE-01 (§9.1b) checks the live answer at the first
real connection.

What it reproduces, deliberately including the cabinet's quirks:
  - two families of /api/ext routes: gateway-proxied (A) and direct (B), with
    their DIFFERENT refusal shapes (A: 403 "Endpoint not allowed"; B: 503
    {"error": "Feature not available", "reason": "Not enabled"} with no detail);
  - a doubled /api/ext/ext/ path answers 401 "Invalid or expired API key",
    the same text as an expired token (NALAZ 1.2);
  - int-typed path params answer FastAPI's 422 before any handler (NALAZ 3.1);
  - Smart Mode OFF: reads work, non-GET writes answer the gateway's 409;
  - opta_connected never goes back to false, so a dead cabinet keeps looking
    "connected" — only the age of last_heartbeat tells the truth (NALAZ 5.1);
  - tokens live 120 minutes and the token response has no expires_in;
  - valves/config always lists two valves, even on a retrofit cabinet;
  - GET /api/nfc/session/{id} and /sessions/by-user both write last_reconciled_at.

Two contracts for channel B (`SimState.contract`):
  - "a709cf8" (default) — what the cabinet code does today: no range read, no
    ack, reads mark sessions reconciled;
  - "r14" — R14 b and c as accepted 2026-10-12: GET /api/nfc/sessions by END
    time (ended_from inclusive, ended_to exclusive, limit/offset), POST
    /api/nfc/sessions/ack, `erp_ref` on the payload, and reads change nothing.
    The query and body names are the ERP's reading (spec §11 O34).

State is a plain object changed through /__sim/* (test-only routes the real
cabinet does not have).
"""
from __future__ import annotations

import copy
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso_z(dt: Optional[datetime]) -> Optional[str]:
    """Cabinet's time_utils.iso_z: microseconds only if non-zero, trailing Z."""
    if dt is None:
        return None
    s = dt.isoformat(timespec="microseconds" if dt.microsecond else "seconds")
    return s + "Z"


TOKEN_MINUTES = 120  # Cloud_IOT config.py:21 jwt_expire_minutes

# api_catalog.py — family B catalog paths are full /api/ext/... paths
FAMILY_B = {
    "pedestals.status_ext": "/api/ext/pedestals/{pedestal_id}/status",
    "water.status_ext": "/api/ext/pedestals/{pedestal_id}/water",
    "berths.occupancy_ext": "/api/ext/pedestals/{pedestal_id}/berths/occupancy",
    "camera.frame_ext": "/api/ext/pedestals/{pedestal_id}/camera/frame",
    "camera.stream_ext": "/api/ext/pedestals/{pedestal_id}/camera/stream",
    "berths.push_image_ext": "/api/ext/pedestals/{pedestal_id}/berths/{berth_id}/image",
    "load.pedestal_get_ext": "/api/ext/pedestals/{pedestal_id}/load",
    "load.socket_get_ext": "/api/ext/pedestals/{pedestal_id}/sockets/{socket_id}/load",
    "load.socket_history_ext": "/api/ext/pedestals/{pedestal_id}/sockets/{socket_id}/load/history",
    "load.pedestal_alarms_ext": "/api/ext/pedestals/{pedestal_id}/load/alarms",
    "load.marina_alarms_ext": "/api/ext/marinas/{marina_id}/load/alarms",
    "load.auto_stop_ack_ext": "/api/ext/pedestals/{pedestal_id}/sockets/{socket_id}/auto-stop/ack",
    "breakers.pedestal_list_ext": "/api/ext/pedestals/{pedestal_id}/breakers",
    "breakers.socket_get_ext": "/api/ext/pedestals/{pedestal_id}/sockets/{socket_id}/breaker",
    "breakers.socket_reset_ext": "/api/ext/pedestals/{pedestal_id}/sockets/{socket_id}/breaker/reset",
    "breakers.pedestal_history_ext": "/api/ext/pedestals/{pedestal_id}/breaker/history",
    "breakers.marina_alarms_ext": "/api/ext/marinas/{marina_id}/breaker/alarms",
}
# int-typed pedestal_id on these direct routes (ext_breaker_*, ext_meter_load_*)
INT_PEDESTAL = {k for k in FAMILY_B if k.startswith(("load.", "breakers."))
                and "marina" not in k}

# family A catalog paths (internal /api/...), method-aware for writes
FAMILY_A = {
    "pedestals.health": ("GET", "/api/pedestals/health"),
    "pedestals.list": ("GET", "/api/pedestals"),
    "berths.list": ("GET", "/api/berths"),
    "sessions.active": ("GET", "/api/sessions/active"),
    "sessions.pending": ("GET", "/api/sessions/pending"),
    "alarms.active": ("GET", "/api/alarms/active"),
    "alarms.acknowledge": ("POST", "/api/alarms/{id}/acknowledge"),
    "analytics.daily": ("GET", "/api/analytics/consumption/daily"),
    "analytics.summary": ("GET", "/api/analytics/sessions/summary"),
    "sockets.config_list": ("GET", "/api/pedestals/{pedestal_id}/sockets/config"),
    "valves.config_list": ("GET", "/api/pedestals/{pedestal_id}/valves/config"),
    "usage.history": ("GET", "/api/pedestals/{pedestal_id}/usage/history"),
    "controls.socket_cmd": ("POST", "/api/controls/pedestal/{pedestal_id}/socket/{socket_name}/cmd"),
    "controls.water_cmd": ("POST", "/api/controls/pedestal/{pedestal_id}/water/{valve_name}/cmd"),
    "controls.allow": ("POST", "/api/controls/{session_id}/allow"),
    "controls.deny": ("POST", "/api/controls/{session_id}/deny"),
    "controls.stop": ("POST", "/api/controls/{session_id}/stop"),
    "diagnostics.run": ("POST", "/api/pedestals/{pedestal_id}/diagnostics/run"),
}
WRITE_KEYS = {k for k, (m, _) in FAMILY_A.items() if m != "GET"}

SMART_MODE_GW_409 = ("Smart Mode is OFF on this pedestal — the API is view-only while the "
                     "cabinet is in standalone control.")  # gw:321-340


@dataclass
class Socket:
    socket_id: int
    phases: int
    rated_amps: float
    plug_inserted: bool = True
    current: float = 0.0
    power_kw: Optional[float] = 0.0
    load_status: str = "normal"
    display_state: str = "idle"
    breaker_state: str = "closed"
    energy_kwh: float = 1200.0       # the meter REGISTER (monotonic), not a session figure


@dataclass
class SimState:
    profile: str = "full"
    pk: int = 1
    display_id: str = "MAR_KRK_ORM_01"
    smart_mode: bool = True
    heartbeat_age_s: float = 5.0
    gateway_active: bool = True
    # what the cabinet operator enabled, and in which mode
    enabled: dict = field(default_factory=dict)
    erp_api_key: Optional[str] = "sim-erp-key"
    service_email: str = "erp@sim.local"
    service_password: str = "sim-password"
    sockets: list = field(default_factory=list)
    berths: list = field(default_factory=list)
    alarms: list = field(default_factory=list)
    sessions: list = field(default_factory=list)      # SessionResponse-shaped (channel A)
    nfc_sessions: dict = field(default_factory=dict)  # 16-key payloads (channel B)
    reconciled: dict = field(default_factory=dict)    # session_id -> count of writes
    # analytics bodies are NOT verified against the cabinet code (not extracted);
    # the ERP only passes them through, nothing reads their keys
    analytics_daily: list = field(default_factory=list)
    analytics_summary: dict = field(default_factory=dict)
    temperature: Optional[float] = 21.5
    moisture: Optional[float] = 40.0
    door_state: str = "closed"
    fail_next: list = field(default_factory=list)     # e.g. [500, 500] or ["timeout"]
    calls: list = field(default_factory=list)         # (method, path) log for tests
    tokens: dict = field(default_factory=dict)        # token -> expiry
    contract: str = "a709cf8"                         # channel B: "a709cf8" | "r14"
    acked: list = field(default_factory=list)         # r14: session ids the ERP confirmed


def _all_enabled() -> dict:
    out = {k: "monitor" for k in FAMILY_B if k not in (
        "breakers.socket_reset_ext", "load.auto_stop_ack_ext", "berths.push_image_ext")}
    for k in FAMILY_A:
        out[k] = "bidirectional" if k in WRITE_KEYS else "monitor"
    return out


def make_state(profile: str = "full") -> SimState:
    s = SimState(profile=profile, enabled=_all_enabled())
    if profile in ("full", "three_phase", "shared_valve", "silent", "smart_off"):
        s.sockets = [Socket(1, 3, 32.0), Socket(2, 1, 32.0), Socket(3, 1, 16.0),
                     Socket(4, 1, 16.0)]
    elif profile == "retrofit":
        s.sockets = [Socket(i, 1, 16.0) for i in (1, 2, 3, 4)]
    else:
        raise ValueError(f"unknown profile {profile}")
    s.berths = [
        _berth(1, "A-01", s.pk, state_code=1),
        _berth(2, "A-02", s.pk, state_code=0),
        _berth(3, "A-03", s.pk, state_code=0),
        _berth(4, "A-04", s.pk, state_code=2),
    ]
    if profile == "silent":
        s.heartbeat_age_s = 11 * 60     # TC-ERP-SIM-05: retained state still looks healthy
    if profile == "smart_off":
        s.smart_mode = False
    return s


def _berth(bid: int, name: str, pk: int, state_code: int) -> dict:
    # BerthOut, berths.py:39-70
    return {
        "id": bid, "name": name, "pedestal_id": pk, "berth_type": "transit",
        "status": "occupied" if state_code else "free", "detected_status": "",
        "last_analyzed": iso_z(_now() - timedelta(minutes=2)),
        "occupied_bit": 1 if state_code else 0, "match_ok_bit": 1 if state_code == 1 else 0,
        "state_code": state_code, "alarm": 1 if state_code == 2 else 0,
        "match_score": 0.91 if state_code == 1 else (0.22 if state_code == 2 else None),
        "analysis_error": None, "confidence": 0.0, "camera_stream_url": None,
        "camera_reachable": True, "reference_image_count": 3,
        "sample_embedding_path": None, "sample_updated_at": None,
        "zone_x1": None, "zone_y1": None, "zone_x2": None, "zone_y2": None,
        "use_detection_zone": 0, "berth_number": bid,
    }


def session_payload(**over) -> dict:
    """build_session_payload, services/nfc_service.py:306-465 — exactly 16 keys."""
    p = {
        "session_id": 101, "cabinet_id": "MAR_KRK_ORM_01", "socket_id": "Q1",
        "session_type": "electricity", "customer_id": "erp-user-7", "status": "ended",
        "activated_at": "2026-10-11T07:00:00Z", "duration_minutes": 95.0,
        "energy_kwh": 3.25, "water_liters": None,
        "meter_energy_start_kwh": 1200.5, "meter_energy_end_kwh": 1203.75,
        "meter_water_start_l": None, "meter_water_end_l": None,
        "consumption_source": "register", "power_kw_current": None,
    }
    p.update(over)
    return p


def _parse_z(v: str) -> datetime:
    return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc)         .replace(tzinfo=None)


def ended_at(p: dict) -> Optional[datetime]:
    """End of an ended session: activated_at + duration_minutes (the payload has no
    ended_at key)."""
    if p.get("status") != "ended" or not p.get("activated_at")             or p.get("duration_minutes") is None:
        return None
    return _parse_z(p["activated_at"]) + timedelta(minutes=float(p["duration_minutes"]))


def _err(status: int, detail: Any) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status)


def _int_422(name: str, value: str) -> JSONResponse:
    # FastAPI's own validation error, raised before the handler
    return JSONResponse({"detail": [{
        "type": "int_parsing", "loc": ["path", name],
        "msg": "Input should be a valid integer, unable to parse string as an integer",
        "input": value}]}, status_code=422)


def _not_enabled_503() -> JSONResponse:
    # direct routes, ext_pedestal_endpoints.py:45-99 — NOTE: no "detail" key
    return JSONResponse({"error": "Feature not available", "reason": "Not enabled"},
                        status_code=503)


def _match(template: str, path: str) -> Optional[dict]:
    t_parts, p_parts = template.strip("/").split("/"), path.strip("/").split("/")
    if len(t_parts) != len(p_parts):
        return None
    out = {}
    for t, p in zip(t_parts, p_parts):
        if t.startswith("{"):
            out[t[1:-1]] = p
        elif t != p:
            return None
    return out


def create_app(state: Optional[SimState] = None) -> FastAPI:
    app = FastAPI(title="cabinet simulator", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.sim = state or make_state("full")

    def sim() -> SimState:
        return app.state.sim

    # ── test-only control routes ─────────────────────────────────────────────
    @app.post("/__sim/profile/{profile}")
    def set_profile(profile: str):
        app.state.sim = make_state(profile)
        return {"profile": profile}

    @app.patch("/__sim/state")
    async def patch_state(request: Request):
        body = await request.json()
        for k, v in body.items():
            if not hasattr(sim(), k):
                return _err(400, f"unknown state field {k}")
            setattr(sim(), k, v)
        return {"ok": True}

    @app.patch("/__sim/socket/{socket_id}")
    async def patch_socket(socket_id: int, request: Request):
        sock = next((k for k in sim().sockets if k.socket_id == socket_id), None)
        if sock is None:
            return _err(404, "no such socket")
        for k, v in (await request.json()).items():
            setattr(sock, k, v)
        return {"ok": True}

    @app.patch("/__sim/credentials")
    async def patch_credentials(request: Request):
        body = await request.json()
        sim().service_email = body["email"]
        sim().service_password = body["password"]
        return {"ok": True}

    @app.post("/__sim/nfc_session")
    async def put_nfc_session(request: Request):
        p = session_payload(**(await request.json()))
        sim().nfc_sessions[p["session_id"]] = p
        return p

    @app.get("/__sim/calls")
    def calls():
        return {"calls": sim().calls, "reconciled": sim().reconciled}

    # ── auth: routers/auth.py:30-69 ──────────────────────────────────────────
    @app.post("/api/auth/service-token")
    async def service_token(request: Request):
        body = await request.json()
        s = sim()
        if body.get("email") != s.service_email or body.get("password") != s.service_password:
            return _err(401, "Invalid email or password")
        tok = secrets.token_hex(16)
        s.tokens[tok] = _now() + timedelta(minutes=TOKEN_MINUTES)
        return {"access_token": tok, "token_type": "bearer", "role": "api_client",
                "email": s.service_email}

    @app.post("/__sim/expire_tokens")
    def expire_tokens():
        sim().tokens = {k: _now() - timedelta(seconds=1) for k in sim().tokens}
        return {"ok": True}

    # ── channel B: routers/nfc.py, auth/erp_api_key.py:20-33 ────────────────
    def _nfc_auth(request: Request) -> Optional[JSONResponse]:
        s = sim()
        if not s.erp_api_key:
            return _err(503, "ERP API not configured")
        if request.headers.get("X-API-Key") != s.erp_api_key:
            return _err(401, "Invalid or missing API key")
        return None

    @app.api_route("/api/nfc/{rest:path}", methods=["GET", "POST"])
    async def nfc(rest: str, request: Request):
        s = sim()
        s.calls.append((request.method, f"/api/nfc/{rest}"))
        if (r := _nfc_auth(request)) is not None:
            return r
        if request.method == "POST" and rest == "scan":
            body = await request.json()
            if not s.smart_mode:
                return _err(409, "This pedestal is running on its own and cannot be switched "
                                 "on remotely. Please ask the marina office to start your socket.")
            outlet = body.get("_outlet", "Q1")   # sim shortcut: tag->outlet mapping lives on the cabinet
            busy = any(p["socket_id"] == outlet and p["status"] == "active"
                       for p in s.nfc_sessions.values())
            if busy:
                word = "socket" if outlet.startswith("Q") else "water outlet"
                return _err(409, f"This {word} is already in use. Please use another {word}.")
            water = outlet.startswith("V")
            return {"status": "pending",
                    "message": "Please open your tap to activate the water outlet" if water
                    else "Please plug in your charger to activate the socket",
                    "cabinet_id": s.display_id, "socket_id": outlet,
                    "outlet_type": "valve" if water else "socket",
                    "session_type": "water" if water else "electricity",
                    "berth_id": None, "expires_at": iso_z(_now() + timedelta(minutes=5))}
        if (m := _match("session/{sid}/stop", rest)) and request.method == "POST":
            p = s.nfc_sessions.get(int(m["sid"])) if m["sid"].isdigit() else None
            if p is None:
                return _err(404, "Session not found")
            if p["status"] != "active":
                return _err(409, "Session already ended by operator")
            p["status"] = "ended"
            return p
        if (m := _match("session/{sid}", rest)) and request.method == "GET":
            p = s.nfc_sessions.get(int(m["sid"])) if m["sid"].isdigit() else None
            if p is None:
                return _err(404, "Session not found")
            if s.contract == "a709cf8":   # mark_reconciled; R14 (4) removes it
                s.reconciled[p["session_id"]] = s.reconciled.get(p["session_id"], 0) + 1
            return p
        if (m := _match("sessions/by-user/{uid}", rest)) and request.method == "GET":
            rows = [p for p in s.nfc_sessions.values() if p.get("customer_id") == m["uid"]]
            if s.contract == "a709cf8":
                for p in rows:
                    s.reconciled[p["session_id"]] = s.reconciled.get(p["session_id"], 0) + 1
            return {"user_id": m["uid"], "count": len(rows), "sessions": rows}
        if s.contract == "r14" and rest == "sessions" and request.method == "GET":
            q = request.query_params
            try:
                frm, to = _parse_z(q["ended_from"]), _parse_z(q["ended_to"])
            except (KeyError, ValueError):
                return _err(422, "ended_from and ended_to are required ISO-8601 UTC")
            limit, offset = int(q.get("limit", 100)), int(q.get("offset", 0))
            rows = sorted((p for p in s.nfc_sessions.values()
                           if (e := ended_at(p)) is not None and frm <= e < to),
                          key=lambda p: (ended_at(p), p["session_id"]))
            return {"sessions": rows[offset:offset + limit], "total": len(rows),
                    "limit": limit, "offset": offset}
        if s.contract == "r14" and rest == "sessions/ack" and request.method == "POST":
            ids = (await request.json()).get("session_ids") or []
            s.acked.extend(int(i) for i in ids)
            return {"acknowledged": len(ids)}
        return _err(404, "Not Found")

    # ── /api/ext/* — gateway (A) and direct routes (B) ───────────────────────
    def _bearer_ok(request: Request) -> Optional[JSONResponse]:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return _err(401, "Missing Authorization header")
        exp = sim().tokens.get(auth[len("Bearer "):])
        if exp is None or exp < _now():
            return _err(401, "Invalid or expired API key")
        return None

    @app.api_route("/api/ext/{rest:path}", methods=["GET", "POST"])
    async def ext(rest: str, request: Request):
        s = sim()
        path = f"/api/ext/{rest}"
        s.calls.append((request.method, path))

        if s.fail_next:
            f = s.fail_next.pop(0)
            if f == "timeout":
                import asyncio
                await asyncio.sleep(30)
            return _err(int(f), "Upstream error: simulated")

        # family B: direct routes win (main.py:904-907)
        for key, tpl in FAMILY_B.items():
            params = _match(tpl, path)
            if params is None:
                continue
            if key in INT_PEDESTAL and not params.get("pedestal_id", "0").isdigit():
                return _int_422("pedestal_id", params["pedestal_id"])
            if "socket_id" in params and not params["socket_id"].isdigit():
                return _int_422("socket_id", params["socket_id"])
            if (r := _bearer_ok(request)) is not None:
                return r
            if not s.gateway_active or key not in s.enabled:
                return _not_enabled_503()
            return _direct(key, params, s)

        # family A through the gateway (gw:203-409)
        if (r := _bearer_ok(request)) is not None:
            return r
        if not s.gateway_active:
            return _err(403, "External API is not active")
        internal = "/api/" + rest
        # doubled ext: internal path is a family-B catalog path; gw proxies with an
        # admin JWT which the direct route rejects (NALAZ 1.2)
        for key, tpl in FAMILY_B.items():
            if _match(tpl, internal) is not None and key in s.enabled:
                return _err(401, "Invalid or expired API key")
        hit = None
        for key, (method, tpl) in FAMILY_A.items():
            if key in s.enabled and (params := _match(tpl, internal)) is not None:
                hit = (key, method, params)   # gw ignores the method when matching (NALAZ 1.3)
                break
        if hit is None:
            return _err(403, "Endpoint not allowed")
        key, method, params = hit
        if request.method != "GET":
            if s.enabled.get(key) != "bidirectional" or key not in WRITE_KEYS:
                return _err(403, "Endpoint is read-only (monitor mode) — only GET allowed")
            if not s.smart_mode:
                return _err(409, SMART_MODE_GW_409)
        body = None
        if request.method == "POST":
            raw = await request.body()
            if raw:
                import json
                body = json.loads(raw)
        return _internal(key, params, body, s)

    return app


def _health(s: SimState) -> dict:
    # pedestal_config.py:397-477 — object keyed by PK (string in JSON)
    hb = _now() - timedelta(seconds=s.heartbeat_age_s)
    feat = {"enabled": True, "available": True, "reason": None}
    return {str(s.pk): {
        "opta_connected": True,     # never set back to false after startup (main.py:600-603)
        "opta_client_id": s.display_id, "smart_mode": s.smart_mode,
        "last_heartbeat": iso_z(hb), "camera_reachable": True,
        "last_camera_check": iso_z(hb), "temp_sensor_reachable": True,
        "last_temp_sensor_check": iso_z(hb),
        "ext_berths_occupancy": dict(feat), "ext_camera_frame": dict(feat),
        "ext_camera_stream": dict(feat),
    }}


def _load(s: SimState, sock: Socket) -> dict:
    # serialize_load_state, routers/meter_load.py:64-107 — snake_case, no camelCase
    d = {
        "pedestal_id": s.pk, "socket_id": sock.socket_id, "meter_type": "sdm630"
        if sock.phases == 3 else "sdm120", "phases": sock.phases, "rated_amps": sock.rated_amps,
        "modbus_address": sock.socket_id, "hw_config_received_at": iso_z(_now()),
        "current_amps": sock.current, "voltage_v": 230.0, "power_kw": sock.power_kw,
        "power_kw_raw": sock.power_kw, "power_factor": 0.97, "energy_kwh": sock.energy_kwh,
        "frequency_hz": 50.0, "load_pct": round(100 * sock.current / sock.rated_amps, 1),
        "load_status": sock.load_status, "meter_load_updated_at": iso_z(_now()),
        "warning_threshold_pct": 60, "critical_threshold_pct": 80,
        "display_state": sock.display_state,
    }
    if sock.phases == 3:
        d.update({"current_l1": sock.current, "current_l2": sock.current,
                  "current_l3": sock.current, "voltage_l1": 230.0, "voltage_l2": 231.0,
                  "voltage_l3": 229.0})
    return d


def _breaker(sock: Socket) -> dict:
    # routers/breakers.py:56-95
    return {"socket_id": sock.socket_id, "breaker_state": sock.breaker_state,
            "breaker_last_trip_at": None, "breaker_trip_cause": None, "breaker_trip_count": 0,
            "breaker_type": "MCB", "breaker_rating": f"{int(sock.rated_amps)}A",
            "breaker_poles": "3P" if sock.phases == 3 else "1P", "breaker_rcd": True,
            "breaker_rcd_sensitivity": "30mA", "breaker_remote_reset": "no",
            "remote_reset_available": False,
            "remote_reset_unavailable_reason": "manual reset — ordinary MCB"}


def _resolve(s: SimState, ref: str) -> Optional[str]:
    # _resolve_pedestal, ext_pedestal_endpoints.py:117-144 — PK or opta_client_id
    if ref == str(s.pk) or ref == s.display_id:
        return s.display_id
    return None


def _direct(key: str, p: dict, s: SimState) -> Response:
    if key in INT_PEDESTAL and int(p["pedestal_id"]) != s.pk:
        return _err(404, "Pedestal not found")
    if key == "pedestals.status_ext":
        disp = _resolve(s, p["pedestal_id"])
        if disp is None:
            return _err(404, "Pedestal not found")
        hb = _now() - timedelta(seconds=s.heartbeat_age_s)
        return JSONResponse({
            "pedestal_id": disp,
            "temperature": {"value": s.temperature, "unit": "°C",
                            "alarm": (s.temperature or 0) > 50, "updated_at": iso_z(hb)},
            "moisture": {"value": s.moisture, "unit": "%",
                         "alarm": (s.moisture or 0) > 90, "updated_at": iso_z(hb)},
            "door_state": s.door_state, "opta_connected": True, "status": "online",
            "last_heartbeat": iso_z(hb)})
    if key == "water.status_ext":
        disp = _resolve(s, p["pedestal_id"])
        if disp is None:
            return _err(404, "Pedestal not found")
        # always two valves — even on a retrofit cabinet (ext_pedestal_endpoints.py:325-377)
        return JSONResponse({"pedestal_id": disp, "valves": [
            {"valve_id": 1, "total_l": None, "session_l": None, "updated_at": None},
            {"valve_id": 2, "total_l": None, "session_l": None, "updated_at": None}],
            "note": "Live valve state/hw_status arrive via the opta_water_status webhook event."})
    if key == "berths.occupancy_ext":
        disp = _resolve(s, p["pedestal_id"])
        if disp is None:
            return _err(404, "Pedestal not found")
        # three shapes, ext_pedestal_endpoints.py:184-205 (NALAZ 4.1)
        if not s.berths:
            return JSONResponse({"pedestal_id": disp, "berths": [],
                                 "message": "No berth definitions found for this pedestal"})
        rows = []
        for b in s.berths:
            if b["last_analyzed"] is None:      # B: no analysis — NO last_analyzed key
                rows.append({"berth_id": b["id"], "berth_name": b["name"], "occupied": None,
                             "note": "No analysis performed yet"})
            else:                               # C: analysed — NO note key
                rows.append({"berth_id": b["id"], "berth_name": b["name"],
                             "occupied": bool(b["occupied_bit"]),
                             "last_analyzed": b["last_analyzed"]})
        return JSONResponse({"pedestal_id": disp, "berths": rows})
    if key == "load.pedestal_get_ext":
        return JSONResponse({"pedestal_id": s.pk, "sockets": [_load(s, k) for k in s.sockets]})
    if key == "load.socket_get_ext":
        sock = next((k for k in s.sockets if k.socket_id == int(p["socket_id"])), None)
        if sock is None:
            return _err(404, "Socket not found on this pedestal")
        return JSONResponse(_load(s, sock))
    if key == "load.pedestal_alarms_ext":
        return JSONResponse({"pedestal_id": s.pk, "alarms": [
            {"id": k.socket_id, "pedestal_id": s.pk, "socket_id": k.socket_id,
             "alarm_type": "auto_stop", "current_amps": k.current, "rated_amps": k.rated_amps,
             "load_pct": 95.0, "phases": k.phases, "meter_type": None,
             "triggered_at": iso_z(_now()), "resolved_at": None, "resolved_by": None,
             "acknowledged": False, "acknowledged_at": None, "acknowledged_by": None}
            for k in s.sockets if k.load_status == "auto_stop"]})
    if key == "breakers.pedestal_list_ext":
        return JSONResponse({"pedestal_id": s.pk, "sockets": [_breaker(k) for k in s.sockets]})
    if key == "breakers.socket_get_ext":
        sock = next((k for k in s.sockets if k.socket_id == int(p["socket_id"])), None)
        body = _breaker(sock) if sock else {"socket_id": int(p["socket_id"]),
                                            "breaker_state": "unknown"}
        return JSONResponse({"pedestal_id": s.pk, **body, "recent_events": []})
    if key == "camera.stream_ext":
        # body NOT verified against the cabinet code (not extracted); only the
        # pass-through is used by the ERP, nothing reads its keys
        return JSONResponse({"pedestal_id": _resolve(s, p["pedestal_id"]),
                             "stream_url": "rtsp://sim/stream", "reachable": True})
    if key == "camera.frame_ext":
        return Response(b"\xff\xd8\xff\xd9", media_type="image/jpeg")
    return JSONResponse({"pedestal_id": s.pk, "alarms": [], "events": []})


def _internal(key: str, p: dict, body: Optional[dict], s: SimState) -> Response:
    def _pk_ok() -> Optional[Response]:
        if not p["pedestal_id"].isdigit():
            return _int_422("pedestal_id", p["pedestal_id"])
        if int(p["pedestal_id"]) != s.pk:
            return _err(404, "Pedestal not found")
        return None

    if key == "pedestals.health":
        return JSONResponse(_health(s))
    if key == "pedestals.list":
        # PedestalResponse — NO display id here; that is opta_client_id in health
        return JSONResponse([{"id": s.pk, "name": "Ormar 1", "location": "Krk",
                              "ip_address": None, "camera_ip": None, "data_mode": "real",
                              "initialized": True, "mobile_enabled": False, "ai_enabled": True}])
    if key == "berths.list":
        return JSONResponse(copy.deepcopy(s.berths))
    if key == "sessions.active":
        return JSONResponse([x for x in s.sessions if x["status"] == "active"])
    if key == "sessions.pending":
        return JSONResponse([x for x in s.sessions if x["status"] == "pending"])
    if key == "alarms.active":
        return JSONResponse([a for a in s.alarms if a["status"] == "triggered"])
    if key == "analytics.daily":
        return JSONResponse(s.analytics_daily)
    if key == "analytics.summary":
        return JSONResponse(s.analytics_summary)
    if key == "sockets.config_list":
        if (r := _pk_ok()) is not None:
            return r
        return JSONResponse([{"socket_id": i, "auto_activate": False} for i in (1, 2, 3, 4)])
    if key == "valves.config_list":
        if (r := _pk_ok()) is not None:
            return r
        # always two valves, also on retrofit (pedestal_config.py:551-572)
        return JSONResponse([{"valve_id": i, "auto_activate": True} for i in (1, 2)])
    if key == "controls.socket_cmd":
        if (r := _pk_ok()) is not None:
            return r
        name = p["socket_name"]
        if name not in ("Q1", "Q2", "Q3", "Q4"):
            return _err(400, "socket_name must be one of Q1, Q2, Q3, Q4")
        action = (body or {}).get("action")
        if action not in ("activate", "stop"):
            return _err(422, [{"type": "string_pattern_mismatch", "loc": ["body", "action"]}])
        sock = next((k for k in s.sockets if k.socket_id == int(name[1])), None)
        if action == "activate" and (sock is None or not sock.plug_inserted):
            return _err(409, "Socket has no plug inserted")  # controls.py:690-700
        return JSONResponse({"status": "sent", "socket": name, "action": action,
                             "nfc_cross_check": "not-supplied"})
    if key == "controls.water_cmd":
        if (r := _pk_ok()) is not None:
            return r
        name = p["valve_name"]
        if name not in ("V1", "V2"):
            return _err(400, "valve_name must be V1 or V2")
        return JSONResponse({"status": "sent", "valve": name,
                             "action": (body or {}).get("action")})
    if key in ("controls.allow", "controls.deny", "controls.stop"):
        sid = p["session_id"]
        row = next((x for x in s.sessions if str(x["id"]) == sid), None)
        if row is None:
            return _err(404, "Session not found")
        want = "active" if key == "controls.stop" else "pending"
        if row["status"] != want:
            return _err(400, f"Session is {row['status']}, expected {want}")
        row["status"] = {"controls.allow": "active", "controls.deny": "denied",
                         "controls.stop": "completed"}[key]
        return JSONResponse(row)
    if key == "alarms.acknowledge":
        row = next((a for a in s.alarms if str(a["id"]) == p["id"] and
                    a["status"] == "triggered"), None)
        if row is None:
            return _err(404, "Alarm not found or already acknowledged")
        row["status"] = "acknowledged"
        return JSONResponse(row)
    return JSONResponse([])


app = create_app()
