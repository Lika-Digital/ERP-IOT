"""The berth list the frontend renders — everything computed here (spec §3, §6.2).

Inputs are cabinet reads (Outcomes) and the ERP's cabinet config. Output, per
berth: status_code / status / berth_colour / status_sentence (berth_status.py),
the outlets that serve it, and `controls` — present ONLY when a control can
actually work. When it cannot (standalone, no contact, stale data, endpoint not
enabled, outlet absent) the key is missing, so the control is missing from the
DOM, not disabled (TC-ERP-SIM-06, SIM-16; D3).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from ..utils.time import utcnow
from . import berth_status as bs
from .cabinet_config import CabinetConfig
from .outcomes import Outcome


def parse_iso(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo else dt   # naive UTC throughout


def parse_occupancy(body: dict) -> list:
    """berths.occupancy_ext has three shapes (NALAZ 4.1); one normalised list.

    A) no berths defined: "berths": [] plus "message"
    B) not analysed: "occupied": null, "note", and NO last_analyzed key
    C) analysed: "occupied": bool, "last_analyzed", and NO note key
    `occupied` None means "not known", never "free".
    """
    out = []
    for b in (body or {}).get("berths") or []:
        occ = b.get("occupied")
        out.append({
            "berth_id": b.get("berth_id"),
            "name": b.get("berth_name"),
            "occupied": occ if isinstance(occ, bool) else None,
            "last_analyzed": b.get("last_analyzed"),
            "note": b.get("note"),
        })
    return out


def _outlet_name(socket_id: int) -> str:
    return f"Q{int(socket_id)}"


def electricity_reading(load: dict) -> dict:
    """One shape for one-phase and three-phase sockets (spec §4.1, TC-ERP-SIM-03).

    The ext API sends snake_case: current_amps / power_kw always, and
    current_l1..l3 only when phases == 3 (meter_load.py:64-107). There is no
    per-phase power. power_kw None means the reading was refused, not 0.
    """
    phases = load.get("phases")
    if phases == 3:
        amps = [load.get("current_l1"), load.get("current_l2"), load.get("current_l3")]
    else:
        amps = [load.get("current_amps")]
    return {
        "phases": phases,
        "rated_amps": load.get("rated_amps"),
        "current_amps": amps,
        "power_kw": load.get("power_kw"),
        "load_status": load.get("load_status"),
        "state": load.get("display_state") or "unknown",
    }


def build(
    *,
    health: Outcome,
    berths: Outcome,
    status: dict,           # pk -> Outcome of pedestals.status_ext
    load: dict,             # pk -> Outcome of load.pedestal_get_ext
    breakers: dict,         # pk -> Outcome of breakers.pedestal_list_ext
    alarms: Optional[Outcome],
    sessions: Optional[Outcome],
    config: CabinetConfig,
    controls_enabled: bool,
    now: Optional[datetime] = None,
) -> dict:
    now = now or utcnow()
    reads = [health, berths, alarms, sessions, *status.values(), *load.values(),
             *breakers.values()]
    stale_reads = [o for o in reads if o is not None and o.is_stale]
    data_is_stale = bool(stale_reads)
    synced_at = min((o.synced_at for o in stale_reads if o.synced_at), default=None)

    cabinets = health.data if health.has_data and isinstance(health.data, dict) else {}
    berth_rows = berths.data if berths.has_data and isinstance(berths.data, list) else []

    def cab(pk) -> dict:
        return cabinets.get(str(pk), {}) if pk is not None else {}

    def st(pk) -> dict:
        o = status.get(pk)
        return o.data if o is not None and o.has_data and isinstance(o.data, dict) else {}

    alarm_types = {}
    for a in (alarms.data if alarms and alarms.has_data else []) or []:
        alarm_types.setdefault(a.get("pedestal_id"), set()).add(a.get("alarm_type"))

    def _sockets(o) -> list:
        return (o.data or {}).get("sockets", []) if o is not None and o.has_data else []

    loads, trips = {}, {}           # (pk, "Q1") -> row / tripped
    for pk, o in load.items():
        for row in _sockets(o):
            loads[(pk, _outlet_name(row["socket_id"]))] = row
    for pk, o in breakers.items():
        for row in _sockets(o):
            trips[(pk, _outlet_name(row["socket_id"]))] = row.get("breaker_state") == "tripped"
    active_power = set()            # (pk, "Q1")
    for srow in (sessions.data if sessions and sessions.has_data else []) or []:
        # electricity only — a water session never makes "power: YES" (§3.1)
        if srow.get("type") == "electricity" and srow.get("socket_id") is not None:
            active_power.add((srow.get("pedestal_id"), _outlet_name(srow["socket_id"])))

    out = []
    for b in berth_rows:
        bid, pk = b.get("id"), b.get("pedestal_id")
        c = cab(pk)
        outlets_here = config.outlets_for(bid)
        elec = [o for o in outlets_here if o.startswith("Q")]
        types = alarm_types.get(pk, set())

        power: Optional[bool] = None
        if elec:
            power = any((pk, o) in active_power for o in elec)
        s_pk = st(pk)

        signals = bs.BerthSignals(
            now=now,
            last_heartbeat=parse_iso(c.get("last_heartbeat")),
            smart_mode=c.get("smart_mode") if c else None,
            data_is_stale=data_is_stale,
            data_synced_at=synced_at,
            water_leak=bool((s_pk.get("moisture") or {}).get("alarm")) or "moisture" in types,
            too_hot=bool((s_pk.get("temperature") or {}).get("alarm")) or "temperature" in types,
            auto_off_overload=any((loads.get((pk, o)) or {}).get("load_status") == "auto_stop"
                                  for o in elec),
            breaker_tripped=any(trips.get((pk, o)) for o in elec),
            state_code=b.get("state_code"),
            last_analyzed=parse_iso(b.get("last_analyzed")),
            power_active=power,
            reserved=None,                      # reservations: phase 3+
        )
        status_row = bs.compute(signals)

        can_control = (controls_enabled and status_row.status_code not in
                       ("no_contact", "standalone", "outlet_silent")
                       and status_row.connection == "ONLINE")

        outlets = []
        for name in outlets_here:
            o = {"name": name, "medium": "electricity" if name.startswith("Q") else "water"}
            if name.startswith("Q"):
                if (pk, name) not in loads:
                    continue                    # the cabinet does not report this socket
                o.update(electricity_reading(loads[(pk, name)]))
                o["breaker_tripped"] = bool(trips.get((pk, name)))
            else:
                o.update({"state": "unknown", "rated_lpm": 20})
            shared = config.berths_sharing(name, bid)
            if shared:
                # supervision clarification only, never a billing note (§9.1 SIM-04)
                o["shared_with_berths"] = shared
            if can_control:
                o["controls"] = ["activate", "stop"]
            outlets.append(o)

        out.append({
            "berth_id": bid,
            "name": b.get("name"),
            "pedestal": {"pk": pk, "display_id": c.get("opta_client_id")},
            **status_row.to_dict(),
            "outlets": outlets,
        })

    return {
        "berths": out,
        "is_stale": data_is_stale,
        "cabinet": {"outcome": health.public(), "configured": config.device_type is not None,
                    "device_type": config.device_type},
    }
