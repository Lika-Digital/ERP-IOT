"""Berth state — computed ONCE, on the server (spec §3, TC-ERP-SIM-05, 06, 15).

Four independent signals (D2), never merged into one another:
  connection  ONLINE | STALE | OFFLINE   from the age of last_heartbeat, computed here
  vessel      NONE | RIGHT | WRONG | UNKNOWN  from berths.list state_code + last_analyzed
  power       YES | NO | UNKNOWN          active ELECTRICITY session on the berth's outlet
  reservation YES | NO | UNKNOWN          ERP reservations (phase 3+)

and one ranked table (§3.2): the highest rank that is true wins. The frontend
never derives a status; it renders `berth_colour` and `status_sentence`.
Tests talk about `status_code`, never about the sentence.

A state with no row in the table is not drawn as free: it becomes
`unclassified` / unknown / grey, "Nešto treba provjeriti" (§3.2).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

OFFLINE_AFTER = timedelta(minutes=10)          # D2
VESSEL_FRESH_FOR = timedelta(minutes=30)       # §3.1
DEFAULT_HEARTBEAT_INTERVAL = timedelta(seconds=60)

# rank, status_code, status, berth_colour, sentence
_TABLE: list[tuple[float, str, str, str, str]] = [
    (1,   "no_contact",           "unknown",   "grey",   "Nema veze s ovim ormarom"),
    (2,   "standalone",           "unknown",   "grey",   "Ormar radi samostalno"),
    (2.5, "outlet_silent",        "unknown",   "grey",   "Ovaj priključak se nije javio"),
    (3,   "water_leak",           "attention", "red",    "Otkriveno curenje vode"),
    (4,   "too_hot",              "attention", "red",    "Ormar je pregrijan"),
    (5,   "auto_off_overload",    "attention", "red",
     "Struja se automatski isključila — preveliko trošenje"),
    (6,   "breaker_tripped",      "attention", "red",    "Struja je iskočila — treba resetirati"),
    (7,   "measurement_missing",  "attention", "red",    "Potrošnja nije izmjerena — treba pregled"),
    (8,   "vessel_mismatch",      "attention", "red",    "Plovilo ne odgovara slici"),
    (9,   "power_without_vessel", "attention", "orange", "Struja teče, a plovila nema"),
    (10,  "reserved_empty",       "attention", "yellow", "Rezervirano, vez je prazan"),
    (11,  "vessel_present",       "ok",        "blue",   ""),
    (12,  "free",                 "ok",        "green",  ""),
]
UNCLASSIFIED = ("unclassified", "unknown", "grey", "Nešto treba provjeriti")

STATUS_CODES = frozenset(r[1] for r in _TABLE) | {UNCLASSIFIED[0]}
_BY_CODE = {r[1]: r for r in _TABLE}


@dataclass(frozen=True)
class BerthSignals:
    """Raw inputs for one berth. None = this input is not known."""
    now: datetime
    last_heartbeat: Optional[datetime]
    smart_mode: Optional[bool]
    data_is_stale: bool = False          # the cabinet did not answer; data is from cache
    data_synced_at: Optional[datetime] = None  # when that cached data was fetched
    outlet_silent: bool = False
    water_leak: bool = False
    too_hot: bool = False
    auto_off_overload: bool = False
    breaker_tripped: bool = False
    measurement_missing: bool = False
    state_code: Optional[int] = None     # 0 FREE, 1 OK, 2 WRONG (berths.list)
    last_analyzed: Optional[datetime] = None
    power_active: Optional[bool] = None  # electricity only; water never counts
    reserved: Optional[bool] = None
    heartbeat_interval: timedelta = DEFAULT_HEARTBEAT_INTERVAL


@dataclass(frozen=True)
class BerthStatus:
    status_code: str
    status: str
    berth_colour: str
    status_sentence: str
    connection: str
    vessel: str
    power: str
    reservation: str
    data_as_of: Optional[str] = None
    signals: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "status_code": self.status_code,
            "status": self.status,
            "berth_colour": self.berth_colour,
            "status_sentence": self.status_sentence,
            "signals": {
                "connection": self.connection,
                "vessel": self.vessel,
                "power": self.power,
                "reservation": self.reservation,
            },
            "data_as_of": self.data_as_of,
        }


def connection_signal(s: BerthSignals) -> str:
    if s.last_heartbeat is None:
        return "OFFLINE"
    age = s.now - s.last_heartbeat
    if age > OFFLINE_AFTER:
        return "OFFLINE"
    if age > 2 * s.heartbeat_interval:
        return "STALE"
    return "ONLINE"


def vessel_signal(s: BerthSignals) -> str:
    if s.state_code is None or s.last_analyzed is None:
        return "UNKNOWN"
    if s.now - s.last_analyzed > VESSEL_FRESH_FOR:
        return "UNKNOWN"
    return {0: "NONE", 1: "RIGHT", 2: "WRONG"}.get(s.state_code, "UNKNOWN")


def _tri(v: Optional[bool]) -> str:
    return "UNKNOWN" if v is None else ("YES" if v else "NO")


def compute(s: BerthSignals) -> BerthStatus:
    connection = connection_signal(s)
    vessel = vessel_signal(s)
    power = _tri(s.power_active)
    reservation = _tri(s.reserved)

    truth = {
        # A cabinet that did not answer just now is "no contact", whatever the
        # cached data says: the cache is what it said, not what it is (§2.5).
        "no_contact": connection == "OFFLINE" or s.data_is_stale,
        "standalone": s.smart_mode is False,
        "outlet_silent": s.outlet_silent,
        "water_leak": s.water_leak,
        "too_hot": s.too_hot,
        "auto_off_overload": s.auto_off_overload,
        "breaker_tripped": s.breaker_tripped,
        "measurement_missing": s.measurement_missing,
        "vessel_mismatch": vessel == "WRONG",
        "power_without_vessel": power == "YES" and vessel == "NONE",
        "reserved_empty": reservation == "YES" and vessel == "NONE",
        "vessel_present": vessel == "RIGHT",
        # free only when the vessel signal positively says NONE; an unknown
        # vessel has no row and must not be drawn green.
        "free": vessel == "NONE",
    }
    for _rank, code, status, colour, sentence in _TABLE:
        if truth[code]:
            break
    else:
        code, status, colour, sentence = UNCLASSIFIED

    as_of = None
    if s.data_is_stale and s.data_synced_at is not None:
        as_of = s.data_synced_at.strftime("%H:%M")
        sentence = f"{sentence} — podaci od {as_of}"

    return BerthStatus(code, status, colour, sentence, connection, vessel, power,
                       reservation, data_as_of=as_of)
