"""The ONE table of cabinet calls: key -> method, path, id type, mode (spec §2.1-§2.4).

Nothing outside this module builds a cabinet URL. The old client prefixed paths
inline (`"/api/ext/" + path`), which put a doubled `ext` one typo away — and a
doubled `ext` answers 401 that is not about credentials (NALAZ 1.2).

Path rule (§2.1): external path = catalog path with `/api/` replaced by
`/api/ext/`, unless the catalog path already starts with `/api/ext/` (family B,
the cabinet's own direct routes), then it is used verbatim. `CATALOG_PATHS`
below holds catalog paths; `external_path()` applies the rule; a test checks
the result against the external paths written in spec §2.2.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class IdType(Enum):
    NONE = "none"          # no pedestal id in the path
    PK = "pk"              # numeric primary key only — display_id gives 422 (NALAZ 3.1)
    PK_OR_DISPLAY = "pk|display"


class Mode(Enum):
    MONITOR = "monitor"            # read
    BIDIRECTIONAL = "bidirectional"  # write; must be enabled as bidirectional on the cabinet


@dataclass(frozen=True)
class Endpoint:
    key: str
    method: str
    catalog_path: str
    id_type: IdType
    mode: Mode
    used_for: str

    @property
    def path(self) -> str:
        return external_path(self.catalog_path)


def external_path(catalog_path: str) -> str:
    if catalog_path.startswith("/api/ext/"):
        return catalog_path
    if not catalog_path.startswith("/api/"):
        raise ValueError(f"catalog path does not start with /api/: {catalog_path}")
    return "/api/ext/" + catalog_path[len("/api/"):]


_M, _B = Mode.MONITOR, Mode.BIDIRECTIONAL
_N, _PK, _PD = IdType.NONE, IdType.PK, IdType.PK_OR_DISPLAY

# Family A: catalog path /api/...   (proxied through the gateway)
# Family B: catalog path /api/ext/... (the cabinet's own routes)
_TABLE = [
    Endpoint("pedestals.health", "GET", "/api/pedestals/health", _N, _M,
             "smart_mode, opta_connected, last_heartbeat"),
    Endpoint("pedestals.list", "GET", "/api/pedestals", _N, _M, "cabinet list, PK + display_id"),
    Endpoint("pedestals.status_ext", "GET", "/api/ext/pedestals/{pedestal_id}/status", _PD, _M,
             "door_state, temperature, moisture"),
    Endpoint("water.status_ext", "GET", "/api/ext/pedestals/{pedestal_id}/water", _PD, _M,
             "valve state and totals"),
    Endpoint("berths.list", "GET", "/api/berths", _N, _M,
             "state_code, match_ok_bit, match_score, last_analyzed"),
    Endpoint("berths.occupancy_ext", "GET", "/api/ext/pedestals/{pedestal_id}/berths/occupancy",
             _PD, _M, "fallback; occupied only"),
    Endpoint("sessions.active", "GET", "/api/sessions/active", _N, _M, "dashboard"),
    Endpoint("sessions.pending", "GET", "/api/sessions/pending", _N, _M, "dashboard"),
    Endpoint("alarms.active", "GET", "/api/alarms/active", _N, _M, "alarm codes for §3"),
    Endpoint("alarms.acknowledge", "POST", "/api/alarms/{alarm_id}/acknowledge", _N, _B,
             "acknowledge from the ERP"),
    Endpoint("analytics.daily", "GET", "/api/analytics/consumption/daily", _N, _M, "check sum"),
    Endpoint("analytics.summary", "GET", "/api/analytics/sessions/summary", _N, _M, "check sum"),
    Endpoint("sockets.config_list", "GET", "/api/pedestals/{pedestal_id}/sockets/config", _PK, _M,
             "capability discovery (D3)"),
    Endpoint("valves.config_list", "GET", "/api/pedestals/{pedestal_id}/valves/config", _PK, _M,
             "capability discovery (D3)"),
    Endpoint("load.pedestal_get_ext", "GET", "/api/ext/pedestals/{pedestal_id}/load", _PK, _M,
             "per-socket telemetry"),
    Endpoint("load.socket_get_ext", "GET",
             "/api/ext/pedestals/{pedestal_id}/sockets/{socket_id}/load", _PK, _M,
             "one socket's telemetry"),
    Endpoint("load.socket_history_ext", "GET",
             "/api/ext/pedestals/{pedestal_id}/sockets/{socket_id}/load/history", _PK, _M,
             "history for the energy agent"),
    Endpoint("load.pedestal_alarms_ext", "GET", "/api/ext/pedestals/{pedestal_id}/load/alarms",
             _PK, _M, "auto_off_overload"),
    Endpoint("load.marina_alarms_ext", "GET", "/api/ext/marinas/{marina_id}/load/alarms", _N, _M,
             "auto_off_overload per marina"),
    Endpoint("breakers.pedestal_list_ext", "GET", "/api/ext/pedestals/{pedestal_id}/breakers",
             _PK, _M, "breaker_tripped"),
    Endpoint("breakers.socket_get_ext", "GET",
             "/api/ext/pedestals/{pedestal_id}/sockets/{socket_id}/breaker", _PK, _M,
             "breaker per socket"),
    Endpoint("breakers.pedestal_history_ext", "GET",
             "/api/ext/pedestals/{pedestal_id}/breaker/history", _PK, _M, "diagnostics"),
    Endpoint("breakers.marina_alarms_ext", "GET", "/api/ext/marinas/{marina_id}/breaker/alarms",
             _N, _M, "breaker alarms per marina"),
    Endpoint("camera.frame_ext", "GET", "/api/ext/pedestals/{pedestal_id}/camera/frame", _PD, _M,
             "berth image on request"),
    Endpoint("camera.stream_ext", "GET", "/api/ext/pedestals/{pedestal_id}/camera/stream", _PD,
             _M, "RTSP URL"),
    Endpoint("usage.history", "GET", "/api/pedestals/{pedestal_id}/usage/history", _PK, _M,
             "reconciliation"),
    Endpoint("controls.socket_cmd", "POST",
             "/api/controls/pedestal/{pedestal_id}/socket/{socket_name}/cmd", _PK, _B,
             "operator path (D3)"),
    Endpoint("controls.water_cmd", "POST",
             "/api/controls/pedestal/{pedestal_id}/water/{valve_name}/cmd", _PK, _B,
             "operator path, water"),
    Endpoint("controls.allow", "POST", "/api/controls/{session_id}/allow", _N, _B, "allow session"),
    Endpoint("controls.deny", "POST", "/api/controls/{session_id}/deny", _N, _B, "deny session"),
    Endpoint("controls.stop", "POST", "/api/controls/{session_id}/stop", _N, _B, "stop session"),
    Endpoint("diagnostics.run", "POST", "/api/pedestals/{pedestal_id}/diagnostics/run", _PK, _B,
             "service window"),
]

ENDPOINTS: dict[str, Endpoint] = {e.key: e for e in _TABLE}

# §2.3 — must NOT be enabled on the cabinet, and the ERP never calls them.
NEVER_ENABLE = frozenset({
    "breakers.socket_reset_ext", "load.auto_stop_ack_ext", "berths.push_image_ext",
    "led_schedule.get", "led_schedule.upsert", "led_schedule.delete", "led_schedule.test",
    "controls.reset", "controls.led", "sockets.config_patch", "valves.config_patch",
    "controls.socket_approve", "controls.socket_reject",
})

# Channel B (§2.4): NFC, direct, X-API-Key, never through /api/ext.
NFC_SCAN = "/api/nfc/scan"
NFC_SESSION = "/api/nfc/session/{session_id}"
NFC_SESSION_STOP = "/api/nfc/session/{session_id}/stop"
# Writes last_reconciled_at on the cabinet (§7.2 R2): reconciliation only, never display.
NFC_SESSIONS_BY_USER = "/api/nfc/sessions/by-user/{user_id}"

_PARAM = re.compile(r"\{(\w+)\}")
_OUTLET = re.compile(r"^(Q[1-4]|V[1-2])$")


class ContractError(ValueError):
    """The ERP is about to send something the contract forbids — an ERP bug."""


def build_path(key: str, **params) -> str:
    """The only way to get a cabinet URL path. Refuses what the cabinet would 422."""
    ep = ENDPOINTS.get(key)
    if ep is None:
        raise ContractError(f"unknown endpoint key {key!r}")
    path = ep.path
    if "/api/ext/ext/" in path:
        raise ContractError(f"doubled ext in {path}")
    needed = set(_PARAM.findall(path))
    if needed != set(params):
        raise ContractError(f"{key}: needs {sorted(needed)}, got {sorted(params)}")
    for name, value in params.items():
        if name == "pedestal_id" and ep.id_type is IdType.PK:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ContractError(f"{key} takes the numeric PK, got {value!r} (NALAZ 3.1)")
        if name in ("socket_name", "valve_name"):
            if not isinstance(value, str) or not _OUTLET.match(value):
                raise ContractError(f"{key}: {name} must be Q1-Q4/V1-V2, got {value!r}")
    return _PARAM.sub(lambda m: str(params[m.group(1)]), path)


def enabled_by_mode() -> dict[Mode, list[str]]:
    """What the cabinet operator must enable in the Gateway UI, and in which mode (§2.3)."""
    out: dict[Mode, list[str]] = {Mode.MONITOR: [], Mode.BIDIRECTIONAL: []}
    for ep in _TABLE:
        out[ep.mode].append(ep.key)
    return out


def endpoint_for(method: str, path: str) -> Optional[Endpoint]:
    """Reverse lookup (used by the simulator and in logs)."""
    for ep in _TABLE:
        pattern = "^" + _PARAM.sub(r"[^/]+", re.escape(ep.path).replace(r"\{", "{").replace(r"\}", "}")) + "$"
        if ep.method == method and re.match(pattern, path):
            return ep
    return None
