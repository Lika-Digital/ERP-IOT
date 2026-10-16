"""The demo marina's world (D28, spec §6.11): layout, and every value as a FUNCTION.

Every simulated value is a function of (seed, device, time) — nothing is
remembered. The same seed and the same moment give the same answer, a restart
changes nothing, and a meter can never go backwards: the register is the
integral of the power profile from a fixed start.

Pure Python, no ERP imports: the simulator serves it (demo_sim.py) and the ERP's
demo seed reads the same layout (app/demo/), so the two can never disagree.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional

# ── layout ───────────────────────────────────────────────────────────────────

# zone, berths, length (m), cabinet kind. Pontoons A–E run from the root at the
# north walkway to the south; quays are QN (north), QS (south), QE (east).
ZONES = (
    ("A", 20, 20.0, "full"), ("B", 20, 15.0, "full"), ("C", 20, 15.0, "full"),
    ("D", 20, 10.0, "full"), ("E", 20, 10.0, "full"),
    ("QN", 25, None, "full"), ("QS", 10, None, "retrofit"), ("QE", 15, None, "full"),
)
# the first pair of A and of B are REAL cabinets (D28); never simulated
REAL = {("A", 1): "MAR_KRK_ORM_01", ("B", 1): "MARINA_IOT_01"}
BERTH_RE = r"^([A-E]|Q[NSE])-\d{2}$"


def berth_id(zone: str, n: int) -> str:
    return f"{zone}-{n:02d}"


@dataclass(frozen=True)
class Berth:
    number: str            # 'E-07'
    zone: str
    index: int             # 1-based within the zone
    length_m: Optional[float]

    @property
    def svg_id(self) -> str:
        return f"berth-{self.number}"


@dataclass(frozen=True)
class CabinetSpec:
    display_id: str        # 'SIM_C_04' or a real one
    zone: str
    pair: int              # 1-based pair index within the zone
    kind: str              # full | retrofit
    berths: tuple          # (Berth, ...) — one or two
    simulated: bool

    def outlets_for(self, slot: int) -> tuple:
        """Outlets of the berth in slot 1 or 2: one socket, and a valve on a full cabinet.
        Q1 (three-phase 32 A) and Q2 (32 A) serve the long berths; Q3/Q4 (16 A) the
        short ones; a retrofit cabinet has four 16 A sockets and no water (D3)."""
        if self.kind == "retrofit":
            return (f"Q{slot}",)
        big = self.berths[0].length_m is not None and self.berths[0].length_m >= 15
        socket = f"Q{slot}" if big else f"Q{slot + 2}"
        return (socket, f"V{slot}")


def berths() -> list[Berth]:
    return [Berth(berth_id(z, i), z, i, length) for z, n, length, _ in ZONES
            for i in range(1, n + 1)]


def cabinets(include_real: bool = False) -> list[CabinetSpec]:
    out = []
    by_zone = {}
    for b in berths():
        by_zone.setdefault(b.zone, []).append(b)
    for z, _n, _length, kind in ZONES:
        bs = by_zone[z]
        for pair in range(1, (len(bs) + 1) // 2 + 1):
            pb = tuple(bs[2 * pair - 2: 2 * pair])
            real = REAL.get((z, pair))
            if real and not include_real:
                continue
            out.append(CabinetSpec(real or f"SIM_{z}_{pair:02d}", z, pair, kind, pb,
                                   simulated=not real))
    return out


# ── deterministic chance ─────────────────────────────────────────────────────

def u(seed: int, *parts) -> float:
    """A uniform number in [0, 1) from the seed and the parts — the same every time."""
    h = hashlib.blake2b(repr((seed,) + parts).encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") / 2 ** 64


EPOCH = datetime(2026, 9, 1, tzinfo=timezone.utc).replace(tzinfo=None)   # meters start; naive UTC
DAY_TURN = timedelta(hours=12)           # boats arrive and leave around midday UTC


def day_of(t: datetime) -> int:
    return (t - EPOCH - DAY_TURN) // timedelta(days=1)


# ── occupancy ────────────────────────────────────────────────────────────────

OCC_LOW, OCC_HIGH = 0.70, 0.85
STAY_DAYS = 3                            # a berth's draw holds for a few days


@lru_cache(maxsize=4096)
def occupied_set(seed: int, day: int) -> frozenset:
    """Exactly k of the 150 berths, k between 70 and 85 % on every day. Ranked by a
    draw that holds for STAY_DAYS per berth, so most boats stay several days."""
    bs = berths()
    k = round(len(bs) * (OCC_LOW + (OCC_HIGH - OCC_LOW) * u(seed, "k", day)))

    def score(b):
        off = int(u(seed, "off", b.number) * STAY_DAYS)
        return u(seed, "stay", b.number, (day + off) // STAY_DAYS)
    return frozenset(b.number for b in sorted(bs, key=score)[:k])


def occupied(seed: int, number: str, t: datetime) -> bool:
    return number in occupied_set(seed, day_of(t))


def wrong_vessel(seed: int, number: str, t: datetime) -> bool:
    return occupied(seed, number, t) and u(seed, "wrong", number, day_of(t)) < 0.03


@lru_cache(maxsize=4096)
def power_without_vessel_of_day(seed: int, day: int) -> str:
    """v21 (T3): every day exactly ONE empty, simulated berth has a cable plugged in with
    no boat, so the demo always shows all six states; picked from the seed and the day."""
    real = {b.number for c in cabinets(include_real=True) if not c.simulated for b in c.berths}
    empty = sorted(b.number for b in berths()
                   if b.number not in occupied_set(seed, day) and b.number not in real)
    return empty[int(u(seed, "pwv-day", day) * len(empty))]


def plugged(seed: int, number: str, t: datetime) -> bool:
    """Power flows: a boat on the berth that plugged in, or a cable with no boat (Power
    without vessel, D2) — one berth a day for certain (T3), and now and then another."""
    d = day_of(t)
    if occupied(seed, number, t):
        return u(seed, "plug", number, d // STAY_DAYS) < 0.8
    return number == power_without_vessel_of_day(seed, d) or u(seed, "pwv", number, d) < 0.02


def reserved(seed: int, number: str, day: int) -> bool:
    """A reservation for an EMPTY berth that day (the ERP's own signal)."""
    return u(seed, "res", number, day) < 0.25


# ── power and the register ───────────────────────────────────────────────────

HOURLY = (0.6, 0.55, 0.5, 0.5, 0.5, 0.55, 0.7, 0.9, 1.0, 0.9, 0.8, 0.7,
          0.7, 0.7, 0.75, 0.8, 0.9, 1.1, 1.3, 1.35, 1.3, 1.1, 0.9, 0.7)   # local evening peak


def base_kw(length_m: Optional[float]) -> float:
    return {20.0: 3.5, 15.0: 2.0, 10.0: 0.9}.get(length_m, 1.2)


def power_kw(seed: int, b: Berth, t: datetime) -> float:
    if not plugged(seed, b.number, t):
        return 0.0
    hour = int((t - EPOCH) // timedelta(hours=1))
    local = (t.hour + 2) % 24            # CEST; the profile only needs a plausible shape
    return round(base_kw(b.length_m) * HOURLY[local] * (0.7 + 0.6 * u(seed, "h", b.number, hour)), 3)


def _hour_kwh(seed: int, b: Berth, hour: int) -> float:
    return power_kw(seed, b, EPOCH + timedelta(hours=hour))


_DAY_KWH: dict = {}       # (seed, berth) -> [kWh before day 0, before day 1, ...]


def _kwh_before_day(seed: int, b: Berth, day0: int) -> float:
    """kWh from EPOCH to the start of calendar day `day0` (counted from EPOCH).
    Built forward once and kept: a register read is a lookup and one partial day."""
    if day0 <= 0:
        return 0.0
    acc = _DAY_KWH.setdefault((seed, b.number), [0.0])
    while len(acc) <= day0:
        d = len(acc) - 1
        acc.append(acc[-1] + sum(_hour_kwh(seed, b, d * 24 + h) for h in range(24)))
    return acc[day0]


def register_kwh(seed: int, b: Berth, t: datetime) -> float:
    """The meter register: monotonic, the integral of power_kw from EPOCH."""
    if t <= EPOCH:
        return round(_e0(seed, b), 4)
    hours = (t - EPOCH) / timedelta(hours=1)
    day0, h_in_day = divmod(int(hours), 24)
    e = _kwh_before_day(seed, b, day0)
    e += sum(_hour_kwh(seed, b, day0 * 24 + h) for h in range(h_in_day))
    e += _hour_kwh(seed, b, int(hours)) * (hours - int(hours))
    return round(_e0(seed, b) + e, 4)


def _e0(seed: int, b: Berth) -> float:
    return 1000.0 + 4000.0 * u(seed, "e0", b.number)


# ── cabinet health and alarms ────────────────────────────────────────────────

def cabinet_alarm(seed: int, cab: CabinetSpec, t: datetime) -> Optional[str]:
    """Now and then a cabinet raises an alarm for an hour or two: about one cabinet
    in fifty on a given day. Returns the cabinet's alarm_type, or None."""
    d = day_of(t)
    if u(seed, "alarm", cab.display_id, d) >= 0.02:
        return None
    on = EPOCH + DAY_TURN + timedelta(days=d, hours=int(u(seed, "alarm_at", cab.display_id, d) * 22))
    length = 1 + int(u(seed, "alarm_len", cab.display_id, d) * 2)
    if on <= t < on + timedelta(hours=length):
        return "moisture" if u(seed, "alarm_kind", cab.display_id, d) < 0.5 else "temperature"
    return None
