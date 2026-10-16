"""The marina as the collector last saw it — from the database, no cabinet call (D23, O64).

The dashboard (§6.6) shows every berth of a marina at once. The Berths screen
before 6a asked the marina's FIRST cabinet live, so a marina of 74 cabinets
showed 2 of 146 linked berths (O64), and an operator's page load would have
been 74 cabinet calls. Here the same berth computation (berth_view, §3.2) runs
over what the collector stored per cabinet server in pedestal_cache.

A stored answer is fresh for CACHE_FRESH_FOR (2 x the slowest read the berth
needs, berths.list and load at 300 s). Older, or the collector's last call to
that server failed, and it counts as "the cabinet did not answer": the berths
of that server go grey with the time of the data (§6.1), never a colour that
looks current.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..models.berth import Berth, BerthOutlet, BerthReservation
from ..models.cabinet import Cabinet, Outlet
from ..models.cache import PedestalCache
from ..utils.time import utcnow
from . import berth_status as bs
from . import berth_view, contract
from .cabinet_config import CabinetConfig
from .client import cache_key
from .outcomes import Outcome

CACHE_FRESH_FOR = timedelta(minutes=10)

# without these the berths of a server cannot be drawn at all; the rest only add to them
_SERVER_REQUIRED = ("pedestals.health", "berths.list")
_SERVER_OPTIONAL = ("alarms.active", "sessions.active")
_CABINET_OPTIONAL = ("pedestals.status_ext", "load.pedestal_get_ext",
                     "breakers.pedestal_list_ext")


def _stored(rows: dict, key: str, base_url: str, now: datetime, required: bool,
            **path_params) -> Optional[Outcome]:
    path = contract.build_path(key, **path_params)
    row = rows.get(f"{cache_key(key, path, None)}@{base_url}")
    if row is None or row.last_seen_data is None:
        return Outcome("no_contact", key, is_stale=True) if required else None
    old = (row.last_synced_at is None or now - row.last_synced_at > CACHE_FRESH_FOR
           or bool(row.is_stale))
    return Outcome("stale" if old else "ok", key, data=row.last_seen_data, is_stale=old,
                   synced_at=row.last_synced_at)


def build(db: Session, marina_id: int, now: Optional[datetime] = None) -> dict:
    """Every berth of the marina: colour, sentence, alarm list, SIM; and every cabinet's
    connection (O51). Berths are in the drawing's order (berths.id)."""
    now = now or utcnow()
    berths = db.query(Berth).filter(Berth.marina_id == marina_id).order_by(Berth.id).all()
    cabs = db.query(Cabinet).filter(Cabinet.marina_id == marina_id).order_by(Cabinet.id).all()
    by_id = {c.id: c for c in cabs}
    rows = {r.cache_key: r for r in db.query(PedestalCache).filter(
        PedestalCache.marina_id == marina_id, PedestalCache.cache_key.isnot(None))}
    reserved_now = {bid for (bid,) in db.query(BerthReservation.berth_id).join(
        Berth, Berth.id == BerthReservation.berth_id).filter(
        Berth.marina_id == marina_id, BerthReservation.starts_at <= now,
        BerthReservation.ends_at > now)}
    outlets_of: dict = {}           # erp berth id -> outlet names
    for berth_id, name in (db.query(BerthOutlet.berth_id, Outlet.outlet_name)
                           .join(Outlet, Outlet.id == BerthOutlet.outlet_id)
                           .join(Berth, Berth.id == BerthOutlet.berth_id)
                           .filter(Berth.marina_id == marina_id)
                           .order_by(Outlet.outlet_name)):
        outlets_of.setdefault(berth_id, []).append(name)

    servers: dict = {}
    for c in cabs:
        servers.setdefault(c.base_url.rstrip("/"), []).append(c)

    computed: dict = {}             # (cabinet id, cabinet berth id) -> berth_view row
    connection: dict = {}           # cabinet id -> ONLINE | STALE | OFFLINE
    for base_url, here in servers.items():
        health, listed = (_stored(rows, k, base_url, now, True) for k in _SERVER_REQUIRED)
        alarms, sessions = (_stored(rows, k, base_url, now, False) for k in _SERVER_OPTIONAL)
        per_cab: dict = {k: {} for k in _CABINET_OPTIONAL}
        for c in here:
            for k in _CABINET_OPTIONAL:
                o = _stored(rows, k, base_url, now, False, pedestal_id=c.pedestal_pk)
                if o is not None:
                    per_cab[k][c.pedestal_pk] = o
        ids = {c.id for c in here}
        mine = [b for b in berths if b.cabinet_id in ids and b.cabinet_berth_id is not None]
        config = CabinetConfig(
            device_type="full" if any(c.device_type == "full" for c in here) else "retrofit",
            berth_outlets={b.cabinet_berth_id: tuple(outlets_of.get(b.id, ())) for b in mine})
        view = berth_view.build(
            health=health, berths=listed, status=per_cab["pedestals.status_ext"],
            load=per_cab["load.pedestal_get_ext"], breakers=per_cab["breakers.pedestal_list_ext"],
            alarms=alarms, sessions=sessions, config=config, controls_enabled=False, now=now,
            reserved={b.cabinet_berth_id for b in mine if b.id in reserved_now})
        pk_to_cab = {c.pedestal_pk: c.id for c in here}
        for row in view["berths"]:
            cid = pk_to_cab.get((row.get("pedestal") or {}).get("pk"))
            if cid is not None:
                computed[(cid, row["berth_id"])] = row
        for c in here:
            connection[c.id] = bs.connection_signal(bs.BerthSignals(
                now=now, last_heartbeat=c.last_heartbeat_at, smart_mode=c.smart_mode))

    out = []
    for b in berths:
        cab = by_id.get(b.cabinet_id)
        row = computed.get((b.cabinet_id, b.cabinet_berth_id)) if cab is not None else None
        if row is None:
            # no cabinet, or the cabinet did not list this berth: nothing is guessed
            st = bs.compute(bs.BerthSignals(now=now, last_heartbeat=None, smart_mode=None,
                                            has_cabinet=cab is not None))
            row = st.to_dict()
        out.append({
            "berth_id": b.id,
            "number": b.berth_number,
            "svg_id": b.svg_id,
            "length_m": float(b.length_m) if b.length_m is not None else None,
            "cabinet": cab.display_id if cab is not None else None,
            "simulated": bool(cab.is_simulated) if cab is not None else False,
            "status_code": row["status_code"],
            "status": row["status"],
            "berth_colour": row["berth_colour"],
            "status_sentence": row["status_sentence"],
            "signals": row["signals"],
            "alarm": row.get("alarm", []),
            "data_as_of": row.get("data_as_of"),
        })
    cabinets = [{
        "display_id": c.display_id,
        "simulated": bool(c.is_simulated),
        "connection": connection.get(c.id, "OFFLINE"),
        "last_heartbeat_at": c.last_heartbeat_at.isoformat() + "Z" if c.last_heartbeat_at else None,
    } for c in cabs]
    return {"berths": out, "cabinets": cabinets}
