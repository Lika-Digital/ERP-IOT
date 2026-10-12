"""Parse the cabinet's per-session payload (spec §2.4).

Contract: Cloud_IOT/docs/erp_session_payload_contract.md v3.47 — exactly 16 keys,
built by one function on the cabinet for GET /api/nfc/session/{id}, by-user,
and the session webhooks.

What this module guarantees, each with a test (TC-ERP-SIM-00, 00c, 00d, 00e, 11, 12, 13):
  - price fields are DROPPED at parse time: they do not exist on the parsed
    object at all, not even as an ignored attribute (D0/D4, §12);
  - `socket_id` is kept as the prefixed string ("Q1", "V1") and checked against
    `session_type` — water is never attributed to an electricity outlet;
  - a null consumption figure is never 0: the session goes to review and is
    not billable;
  - the figure is recomputed from the two meter registers; a disagreement is a
    finding and the session goes to review;
  - consumption_source == "unknown" goes to review (status measurement_missing).
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

CONTRACT_KEYS = frozenset({
    "session_id", "cabinet_id", "socket_id", "session_type", "customer_id",
    "status", "activated_at", "duration_minutes", "energy_kwh", "water_liters",
    "meter_energy_start_kwh", "meter_energy_end_kwh",
    "meter_water_start_l", "meter_water_end_l",
    "consumption_source", "power_kw_current",
})

# R14 (3): the cabinet adds `erp_ref` — the ERP's own reference, sent in /scan.
# Known, so not an "unknown key"; when present it may replace customer_id.
OPTIONAL_KEYS = frozenset({"erp_ref"})

# Dropped at parse time and never stored (spec §2.4, §12). Absence, not ignoring.
PRICE_KEYS = frozenset({"estimated_cost", "cost", "price", "amount"})

CONSUMPTION_SOURCES = frozenset({"register", "integrated_legacy", "unknown"})

_OUTLET_RE = re.compile(r"^(Q[1-4]|V[1-2])$")

# Registers are floats; a recompute that differs by less than this is rounding.
RECOMPUTE_TOLERANCE = 0.001


@dataclass(frozen=True)
class Finding:
    code: str
    detail: str


@dataclass(frozen=True)
class ParsedSession:
    cabinet_session_id: int
    cabinet_display_id: Optional[str]
    outlet_name: Optional[str]          # "Q1".."Q4" | "V1" | "V2" — never a bare number
    session_type: str                   # "electricity" | "water"
    customer_id: Optional[str]
    status: str                         # "active" | "ended"
    activated_at: Optional[str]
    duration_minutes: Optional[float]
    consumption: Optional[float]        # kWh or litres per session_type; None = not known
    unit: str                           # "kWh" | "L"
    meter_start: Optional[float]
    meter_end: Optional[float]
    consumption_source: Optional[str]
    power_kw_current: Optional[float]   # live only; None = reading refused, NOT 0
    manual_review: bool
    findings: tuple[Finding, ...] = field(default_factory=tuple)
    erp_ref: Optional[str] = None       # R14: the ERP's reference, when the cabinet has b

    @property
    def billable(self) -> bool:
        """Only an ended session with a checked figure and no findings."""
        return (
            self.status == "ended"
            and not self.manual_review
            and self.consumption is not None
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["findings"] = [asdict(f) for f in self.findings]
        d["billable"] = self.billable
        return d


class PayloadError(ValueError):
    """The payload cannot be interpreted at all (not a review case — a contract break)."""


def _num(v: Any, key: str) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise PayloadError(f"{key} is not a number: {v!r}")
    return float(v)


def parse_session(raw: dict) -> ParsedSession:
    if not isinstance(raw, dict):
        raise PayloadError("session payload is not an object")

    # Drop prices first, so no code path below can even see them.
    payload = {k: v for k, v in raw.items() if k not in PRICE_KEYS}

    findings: list[Finding] = []
    dropped = len(PRICE_KEYS & raw.keys())
    if dropped:
        # Count only: the name or value of a price must not survive anywhere,
        # not even in a finding — whoever reads it later would take it as real.
        findings.append(Finding("price_field_dropped", f"{dropped} field(s)"))

    # the cabinet's new contract (eac7aa2) carries the KEY erp_ref instead of customer_id;
    # erp_ref may be null — a session the ERP did not start, not a broken payload
    required = CONTRACT_KEYS - ({"customer_id"} if "erp_ref" in payload else set())
    missing = sorted(required - payload.keys())
    if missing:
        raise PayloadError(f"payload is missing contract keys: {', '.join(missing)}")
    extra = sorted(payload.keys() - CONTRACT_KEYS - OPTIONAL_KEYS)
    if extra:
        findings.append(Finding("unknown_keys", ", ".join(extra)))

    session_type = payload["session_type"]
    if session_type not in ("electricity", "water"):
        raise PayloadError(f"session_type is {session_type!r}")

    outlet = payload["socket_id"]
    if outlet is not None:
        if not isinstance(outlet, str) or not _OUTLET_RE.match(outlet):
            # A bare number cannot be attributed: Q1 and V1 are both 1 on the cabinet.
            raise PayloadError(f"socket_id must be Q1-Q4 or V1-V2, got {outlet!r}")
        expected = "Q" if session_type == "electricity" else "V"
        if outlet[0] != expected:
            raise PayloadError(f"socket_id {outlet} does not match session_type {session_type}")

    if session_type == "electricity":
        figure_key, start_key, end_key, unit = (
            "energy_kwh", "meter_energy_start_kwh", "meter_energy_end_kwh", "kWh")
        other_key = "water_liters"
    else:
        figure_key, start_key, end_key, unit = (
            "water_liters", "meter_water_start_l", "meter_water_end_l", "L")
        other_key = "energy_kwh"

    figure = _num(payload[figure_key], figure_key)
    start = _num(payload[start_key], start_key)
    end = _num(payload[end_key], end_key)
    if payload[other_key] is not None:
        findings.append(Finding("cross_medium_figure",
                                f"{other_key} is set on a {session_type} session"))

    source = payload["consumption_source"]
    if source is not None and source not in CONSUMPTION_SOURCES:
        findings.append(Finding("unknown_consumption_source", repr(source)))

    status = payload["status"]
    review = False

    if status == "ended":
        if figure is None:
            # null is "we do not know", never 0 (contract: DO NOT BILL THIS SESSION)
            review = True
            findings.append(Finding("figure_null", f"{figure_key} is null on an ended session"))
        if source == "unknown":
            review = True
            findings.append(Finding("measurement_missing", "consumption_source is 'unknown'"))
        if source == "integrated_legacy":
            review = True
            findings.append(Finding("approximate_figure", "consumption_source is 'integrated_legacy'"))

    if figure is not None:
        if start is None or end is None:
            review = True
            findings.append(Finding("recompute_impossible",
                                    f"{figure_key} given without both meter registers"))
        else:
            delta = end - start
            if abs(delta - figure) > RECOMPUTE_TOLERANCE:
                review = True
                findings.append(Finding(
                    "recompute_mismatch",
                    f"{figure_key}={figure} but {end_key}-{start_key}={delta:.4f}",
                ))

    return ParsedSession(
        cabinet_session_id=int(payload["session_id"]),
        cabinet_display_id=payload["cabinet_id"],
        outlet_name=outlet,
        session_type=session_type,
        customer_id=payload.get("customer_id"),
        status=status,
        activated_at=payload["activated_at"],
        duration_minutes=_num(payload["duration_minutes"], "duration_minutes"),
        consumption=figure,
        unit=unit,
        meter_start=start,
        meter_end=end,
        consumption_source=source,
        power_kw_current=_num(payload["power_kw_current"], "power_kw_current"),
        manual_review=review,
        findings=tuple(findings),
        erp_ref=payload.get("erp_ref") or None,
    )
