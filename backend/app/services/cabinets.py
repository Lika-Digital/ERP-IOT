"""Cabinets, outlets, berths and the ERP side of the mapping (spec §4.1-§4.3, D1, D3, D18).

Every write that changes "whose consumption lands where" takes an actor and
refuses to run without one (D1, D18: never a default).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from ..models.berth import Berth, BerthOutlet, BerthOutletCabinet, MappingComparison
from ..models.cabinet import Cabinet, CabinetCapability, Outlet
from ..utils.encryption import encrypt_password
from ..utils.time import utcnow


class DomainError(ValueError):
    """A rule of the model was about to be broken; the message says which."""


# D3: what each device type physically has. The cabinet does not report this
# (spec §0.7 #3), so it is ERP data, fixed at provisioning.
OUTLETS_BY_TYPE = {
    "full": [
        dict(outlet_name="Q1", medium="electricity", phases=3, rated_amps=32),
        dict(outlet_name="Q2", medium="electricity", phases=1, rated_amps=32),
        dict(outlet_name="Q3", medium="electricity", phases=1, rated_amps=16),
        dict(outlet_name="Q4", medium="electricity", phases=1, rated_amps=16),
        dict(outlet_name="V1", medium="water", rated_lpm=20),
        dict(outlet_name="V2", medium="water", rated_lpm=20),
    ],
    # retrofit: sockets only; ratings are whatever the host cabinet has — unknown here
    "retrofit": [dict(outlet_name=f"Q{i}", medium="electricity") for i in (1, 2, 3, 4)],
}
CAPABILITIES_BY_TYPE = {
    "full": {"power": True, "water": True, "vessel_detect": True, "camera": True,
             "door": True, "breaker": True, "load_meter": True},
    "retrofit": {"power": True, "water": False, "vessel_detect": False, "camera": False,
                 "door": False, "breaker": True, "load_meter": True},
}


def _actor(actor: Optional[str]) -> str:
    if actor is None or not str(actor).strip():
        raise DomainError("an actor is required: who made this change is always recorded")
    return str(actor).strip()


def provision_cabinet(db: Session, *, marina_id: int, pedestal_pk: int, display_id: str,
                      device_type: str, base_url: str, service_email: str,
                      service_password: str, erp_api_key: Optional[str] = None,
                      dock: Optional[str] = None) -> Cabinet:
    if device_type not in OUTLETS_BY_TYPE:
        raise DomainError(f"device_type must be full|retrofit, got {device_type!r}")
    cab = Cabinet(marina_id=marina_id, pedestal_pk=pedestal_pk, display_id=display_id,
                  device_type=device_type, base_url=base_url.rstrip("/"),
                  service_email=service_email, service_pw_enc=encrypt_password(service_password),
                  erp_api_key_enc=encrypt_password(erp_api_key) if erp_api_key else None,
                  dock=dock)
    db.add(cab)
    db.flush()
    for spec in OUTLETS_BY_TYPE[device_type]:
        db.add(Outlet(cabinet_id=cab.id, **spec))
    now = utcnow()
    for cap, available in CAPABILITIES_BY_TYPE[device_type].items():
        db.add(CabinetCapability(cabinet_id=cab.id, capability=cap, available=available,
                                 checked_at=now))
    db.add(MappingComparison(cabinet_id=cab.id, state="unverifiable", checked_at=now))
    db.commit()
    db.refresh(cab)
    return cab


def outlet(db: Session, cabinet_id: int, name: str) -> Outlet:
    o = db.query(Outlet).filter(Outlet.cabinet_id == cabinet_id,
                                Outlet.outlet_name == name).first()
    if o is None:
        raise DomainError(f"cabinet {cabinet_id} has no outlet {name}")
    return o


def create_berth(db: Session, *, marina_id: int, berth_number: str,
                 cabinet_id: Optional[int] = None, cabinet_berth_id: Optional[int] = None,
                 svg_id: Optional[str] = None) -> Berth:
    if (cabinet_id is None) != (cabinet_berth_id is None):
        raise DomainError("cabinet_id and cabinet_berth_id go together")
    if cabinet_id is not None:
        cab = db.get(Cabinet, cabinet_id)
        if cab is None or cab.marina_id != marina_id:
            raise DomainError(f"cabinet {cabinet_id} is not in marina {marina_id}")
    b = Berth(marina_id=marina_id, berth_number=berth_number, svg_id=svg_id,
              cabinet_id=cabinet_id, cabinet_berth_id=cabinet_berth_id)
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


def set_berth_outlets(db: Session, berth: Berth, outlet_names: list[str], *,
                      assigned_by: Optional[str], source: str = "erp_manual") -> list[BerthOutlet]:
    """Replace the ERP's mapping for one berth. The database enforces D1; this
    function gives the human-readable refusal first and then re-compares (D18)."""
    actor = _actor(assigned_by)
    if berth.cabinet_id is None:
        raise DomainError("the berth is not linked to a cabinet")
    cab = db.get(Cabinet, berth.cabinet_id)
    outs = [outlet(db, cab.id, n) for n in outlet_names]
    elec = [o for o in outs if o.medium == "electricity"]
    if len(elec) > 1:
        raise DomainError("a berth has at most one electricity outlet (D1)")
    for o in elec:
        taken = (db.query(BerthOutlet)
                 .filter(BerthOutlet.outlet_id == o.id, BerthOutlet.berth_id != berth.id).first())
        if taken is not None:
            other = db.get(Berth, taken.berth_id)
            raise DomainError(f"{o.outlet_name} already serves berth {other.berth_number} (D1)")
    db.query(BerthOutlet).filter(BerthOutlet.berth_id == berth.id).delete()
    now = utcnow()
    rows = [BerthOutlet(berth_id=berth.id, outlet_id=o.id, medium=o.medium, source=source,
                        assigned_by=actor, assigned_at=now) for o in outs]
    db.add_all(rows)
    db.commit()
    compare_mapping(db, cab.id)
    return rows


@dataclass(frozen=True)
class Comparison:
    state: str
    divergent: list


def compare_mapping(db: Session, cabinet_id: int) -> Comparison:
    """D18: compare the ERP's mapping with what the cabinet claims.

    While no read endpoint exists on the cabinet (R1), there is no cabinet side
    at all — and the answer is 'unverifiable', NEVER 'in_sync' (§4.3).
    """
    cab_rows = db.query(BerthOutletCabinet).filter(
        BerthOutletCabinet.cabinet_id == cabinet_id).all()
    if not cab_rows:
        state, divergent = "unverifiable", []
    else:
        erp = {}
        q = (db.query(Outlet.outlet_name, Berth.cabinet_berth_id)
             .join(BerthOutlet, BerthOutlet.outlet_id == Outlet.id)
             .join(Berth, Berth.id == BerthOutlet.berth_id)
             .filter(Outlet.cabinet_id == cabinet_id))
        for name, cab_berth in q:
            erp.setdefault(name, set()).add(cab_berth)
        theirs = {}
        for r in cab_rows:
            theirs.setdefault(r.outlet_name, set()).add(r.cabinet_berth_id)
        divergent = [
            {"outlet_name": n, "erp_berths": sorted(x for x in erp.get(n, set()) if x is not None),
             "cabinet_berths": sorted(x for x in theirs.get(n, set()) if x is not None)}
            for n in sorted(set(erp) | set(theirs)) if erp.get(n, set()) != theirs.get(n, set())
        ]
        state = "divergent" if divergent else "in_sync"
    row = db.get(MappingComparison, cabinet_id) or MappingComparison(cabinet_id=cabinet_id)
    row.state, row.divergent_rows, row.checked_at = state, divergent or None, utcnow()
    db.add(row)
    db.commit()
    return Comparison(state, divergent)
