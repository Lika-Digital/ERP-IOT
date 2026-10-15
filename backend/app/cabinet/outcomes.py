"""Every way a cabinet call can end — one code, one sentence (spec §2.5).

The client never lets an httpx exception reach a router. A router receives an
`Outcome` and turns it into an ERP response; the frontend shows `sentence`.
Tests compare `code`, never the sentence (§3: sentences stay editable).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

SENTENCES = {
    "ok": "",
    "cabinet_auth_failed": "The cabinet does not accept our sign-in.",
    "not_enabled": "This function is not enabled on the cabinet.",
    "standalone": "The cabinet is running on its own. Marina staff can control it once it reconnects.",
    "awaiting_plug": "Plug in the cable to start.",
    "outlet_busy": "Someone else is using this outlet right now.",
    "nfc_mapping_mismatch": "The tag does not belong to this outlet — switching on was refused.",
    "already_ended": "",                     # staff closed it first — not an error (D10)
    "session_state_changed": "The session changed in the meantime. Refresh the view.",
    "not_found": "The cabinet does not know this record.",
    "conflict": "The cabinet refused the command.",
    "erp_bug": "Technical error, reported.",
    "capability_unavailable": "This feature is not available on the cabinet right now.",
    "stale": "The cabinet is not answering — showing the last known data.",
    "no_contact": "No connection to this cabinet.",
}

# Outcomes that are not failures of the ERP or the cabinet; they are states.
NOT_ERRORS = frozenset({"ok", "already_ended", "standalone", "awaiting_plug", "outlet_busy",
                        "capability_unavailable", "not_enabled", "stale"})


@dataclass(frozen=True)
class Outcome:
    code: str
    endpoint_key: str
    data: Any = None
    http_status: Optional[int] = None
    is_stale: bool = False
    synced_at: Optional[datetime] = None
    cabinet_detail: Optional[str] = None   # the cabinet's own text, for logs only

    @property
    def ok(self) -> bool:
        return self.code == "ok"

    @property
    def sentence(self) -> str:
        return SENTENCES[self.code]

    @property
    def has_data(self) -> bool:
        return self.data is not None and self.code in ("ok", "stale")

    def public(self) -> dict:
        """What an ERP endpoint may return about the outcome."""
        return {
            "code": self.code,
            "sentence": self.sentence,
            "endpoint": self.endpoint_key,
            "is_stale": self.is_stale,
            "data_as_of": self.synced_at.isoformat() + "Z" if self.synced_at else None,
        }


def classify_409(detail: str) -> str:
    """The cabinet's 409s, by their exact text at Cloud_IOT a709cf8."""
    d = detail or ""
    if d.startswith("Smart Mode is OFF") or d.startswith("This pedestal is running on its own"):
        return "standalone"            # gw:321-340, controls.py:324-339, nfc.py scan
    if d == "Socket has no plug inserted":
        return "awaiting_plug"         # controls.py:690-700
    if d == "Session already ended by operator":
        return "already_ended"         # nfc.py:762-790
    if "is already in use" in d or "already has an active session" in d \
            or "being held for them" in d:
        return "outlet_busy"           # nfc.py scan, controls.py:368
    if d.startswith("NFC tag ") and " is mapped to " in d:
        return "nfc_mapping_mismatch"  # controls.py:566-646
    return "conflict"


def classify_400(detail: str) -> str:
    d = detail or ""
    if d.startswith("Session is ") and ", expected " in d:
        return "session_state_changed"   # controls.py:176-319
    # "socket_name must be one of …", "valve_name must be …" — we sent something wrong
    return "erp_bug"
