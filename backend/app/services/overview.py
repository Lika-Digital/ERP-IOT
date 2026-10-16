"""The main dashboard in one answer: map, three cards, cabinets (D23, spec §6.6).

Every number, its freshness and its sentence are decided here; the frontend only
shows them. A card is `fresh`, `partial` (part of the marina is silent: the number
is shown with the word "Partial" and how many are silent) or `stale` (grey, the
time of the last data, no number in full colour) — an old number must not look new.

Simulated (D28) is never mixed in silently: each card says `simulated` = none |
some | all, and the security card counts simulated alarms apart ("+1 SIM").
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..cabinet import marina_state
from ..models.cabinet import Cabinet, Outlet
from ..models.marina import Marina
from ..models.metering import ConsumptionInterval, OutletMeterState
from ..models.security import SecurityAgentPass, SecurityAlarm
from ..utils.time import utcnow

# 2 x the load.* poll (300 s): older than this, the energy figure is not "today so far"
ENERGY_FRESH_FOR = timedelta(minutes=10)
# 2 x the agent's interval (deploy/erp-agent.service: --every 300)
AGENT_FRESH_FOR = timedelta(minutes=10)
OCCUPIED = ("vessel_present", "vessel_mismatch")
# a cabinet alarm on a berth, as the security card weighs it (§1.2 (a): counted there)
CABINET_ALARM_SEVERITY = {"water_leak": "critical", "too_hot": "critical"}
SEVERITY_ORDER = ("critical", "warning", "info")


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


def _hhmm(dt: datetime, tz) -> str:
    return dt.replace(tzinfo=timezone.utc).astimezone(tz).strftime("%H:%M")


def _zone(name: Optional[str]):
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc


def local_midnight_utc(now: datetime, tz) -> datetime:
    """00:00 of the marina's local day containing `now`, as naive UTC."""
    local = now.replace(tzinfo=timezone.utc).astimezone(tz)
    start = datetime.combine(local.date(), time(0), tzinfo=tz)
    return start.astimezone(timezone.utc).replace(tzinfo=None)


def _simulated(n_sim: int, n_all: int) -> str:
    return "none" if n_sim == 0 else ("all" if n_sim == n_all else "some")


def energy_between(db: Session, outlet_ids: list, start: datetime, end: datetime) -> Decimal:
    """kWh in [start, end): whole intervals inside, a straddling one pro rata by time.
    Null is not zero (D10): an interval with no figure adds nothing and is not a 0."""
    if not outlet_ids or end <= start:
        return Decimal(0)
    total = Decimal(0)
    for f, t, e in (db.query(ConsumptionInterval.from_at, ConsumptionInterval.to_at,
                             ConsumptionInterval.energy_kwh)
                    .filter(ConsumptionInterval.outlet_id.in_(outlet_ids),
                            ConsumptionInterval.to_at > start, ConsumptionInterval.from_at < end,
                            ConsumptionInterval.energy_kwh.isnot(None))):
        span = (t - f).total_seconds()
        if span <= 0:
            continue
        inside = (min(t, end) - max(f, start)).total_seconds()
        total += Decimal(e) * Decimal(inside / span) if inside < span else Decimal(e)
    return total


def _delta(today: Decimal, then: Decimal) -> Optional[float]:
    if then <= 0:
        return None
    return round(float((today - then) / then * 100), 1)


def energy_card(db: Session, marina: Marina, now: datetime) -> dict:
    tz = _zone(marina.timezone)
    cabs = db.query(Cabinet.id, Cabinet.is_simulated).filter(Cabinet.marina_id == marina.id).all()
    sim = {cid for cid, s in cabs if s}
    outs = db.query(Outlet.id, Outlet.cabinet_id).filter(
        Outlet.cabinet_id.in_([c for c, _ in cabs]), Outlet.medium == "electricity").all()
    ids = [o for o, _ in outs]
    start = local_midnight_utc(now, tz)
    today = energy_between(db, ids, start, now)
    yesterday = energy_between(db, ids, start - timedelta(days=1), now - timedelta(days=1))
    last_week = energy_between(db, ids, start - timedelta(days=7), now - timedelta(days=7))

    newest_by_cab = dict(db.query(Outlet.cabinet_id, func.max(OutletMeterState.read_at))
                         .join(OutletMeterState, OutletMeterState.outlet_id == Outlet.id)
                         .filter(Outlet.id.in_(ids)).group_by(Outlet.cabinet_id).all()) if ids else {}
    metered = {c for _o, c in outs}
    silent = sorted(c for c in metered
                    if newest_by_cab.get(c) is None or now - newest_by_cab[c] > ENERGY_FRESH_FOR)
    as_of = max((v for v in newest_by_cab.values() if v), default=None)

    card = {
        "key": "energy",
        "title": "Electricity & Water",
        "electricity_kwh": float(round(today, 1)),
        "water_m3": None,              # O62: no water history yet — shown as "—", never 0
        "delta_yesterday_pct": _delta(today, yesterday),
        "delta_last_week_pct": _delta(today, last_week),
        "as_of": _iso(as_of),
        "silent": len(silent),
        "of": len(metered),
        "simulated": _simulated(len(metered & sim), len(metered)),
        "href": "energy",
    }
    if not metered:
        card.update(state="stale", sentence="No metered outlet in this marina yet")
    elif len(silent) == len(metered):
        card.update(state="stale", sentence=(
            f"No meter reading since {_hhmm(as_of, tz)}" if as_of else "No meter reading yet"))
    elif silent:
        card.update(state="partial", sentence=f"{len(silent)} of {len(metered)} cabinets silent")
    else:
        card.update(state="fresh", sentence="Today since 00:00, local time")
    return card


def security_card(db: Session, marina: Marina, berths: list, now: datetime) -> dict:
    tz = _zone(marina.timezone)
    open_rows = (db.query(SecurityAlarm.severity, SecurityAlarm.simulated)
                 .filter(SecurityAlarm.state.in_(("open", "acknowledged"))).all())
    real = [s for s, simulated in open_rows if not simulated]
    sim = sum(1 for _s, simulated in open_rows if simulated)
    for b in berths:
        for a in b["alarm"]:
            sev = CABINET_ALARM_SEVERITY.get(a["code"], "warning")
            if b["simulated"]:
                sim += 1
            else:
                real.append(sev)
    worst = next((s for s in SEVERITY_ORDER if s in real), None)
    last_pass = db.query(func.max(SecurityAgentPass.finished_at)).scalar()
    card = {
        "key": "security",
        "title": "Safety & Security",
        "open": len(real),
        "open_simulated": sim,
        "worst": worst,
        "as_of": _iso(last_pass),
        "simulated": "some" if sim else "none",
        "href": "security",
    }
    if last_pass is None or now - last_pass > AGENT_FRESH_FOR:
        card.update(state="stale", sentence=(
            f"The security agent has been silent since {_hhmm(last_pass, tz)}" if last_pass
            else "The security agent has not run yet"))
    elif not real:
        card.update(state="fresh", sentence="No open alerts" if not sim
                    else "No real open alerts — the simulated ones are counted apart")
    else:
        card.update(state="fresh", sentence=f"Worst: {worst.capitalize()}")
    return card


def occupancy_card(marina: Marina, berths: list, cabinets_polled: Optional[datetime],
                   now: datetime) -> dict:
    tz = _zone(marina.timezone)
    # v21, T1: a berth with no cabinet yet is neither known nor unknown — counted apart
    known = [b for b in berths if b["berth_colour"] not in ("grey", "none")]
    occupied = sum(1 for b in known if b["status_code"] in OCCUPIED)
    unknown = sum(1 for b in berths if b["berth_colour"] == "grey")
    not_connected = sum(1 for b in berths if b["berth_colour"] == "none")
    silent = sum(1 for b in berths if b["status_code"] == "no_contact")
    reserved = sum(1 for b in berths if b["signals"]["reservation"] == "YES")
    n_sim = sum(1 for b in known if b["simulated"])
    card = {
        "key": "occupancy",
        "title": "Occupancy",
        "percent": round(occupied * 100 / len(known)) if known else None,
        "occupied": occupied,
        "known": len(known),
        "unknown": unknown,
        "not_connected": not_connected,
        "reserved": reserved,
        "silent": silent,
        "as_of": _iso(cabinets_polled),
        "simulated": _simulated(n_sim, len(known)),
        "href": "berths",
    }
    if not known:
        card.update(state="stale", sentence=(
            f"No berth state since {_hhmm(cabinets_polled, tz)}" if cabinets_polled
            else "No berth state yet"))
    elif silent:
        card.update(state="partial", sentence=f"{silent} berths on silent cabinets")
    else:
        card.update(state="fresh", sentence="Vessels on berths whose state is known")
    return card


def build(db: Session, marina: Marina, now: Optional[datetime] = None) -> dict:
    now = now or utcnow()
    state = marina_state.build(db, marina.id, now)
    polled = db.query(func.max(Cabinet.last_polled_at)).filter(
        Cabinet.marina_id == marina.id).scalar()
    return {
        "marina_id": marina.id,
        "marina_name": marina.name,
        "map_svg": marina.map_svg,
        "generated_at": _iso(now),
        "cards": [energy_card(db, marina, now), security_card(db, marina, state["berths"], now),
                  occupancy_card(marina, state["berths"], polled, now)],
        "berths": state["berths"],
        "cabinets": state["cabinets"],
    }
