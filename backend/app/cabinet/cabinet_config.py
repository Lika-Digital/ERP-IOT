"""What the ERP knows about a cabinet that the cabinet does not say (spec §0.7 #3, §4.1).

The cabinet API does not tell whether it has water (valves/config always lists
two valves, also on a retrofit) nor which outlets serve which berth (NALAZ 4.2).
Both are ERP data: `cabinets.device_type` and `berth_outlets` (phase 3). In
phase 2 they came from a JSON file (ERP_CABINETS_FILE); that file is gone.

No cabinet row for the marina -> nothing is guessed: no water is drawn, and the
power signal of every berth is UNKNOWN.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class CabinetConfig:
    device_type: Optional[str] = None                 # None = no cabinet provisioned
    berth_outlets: dict = field(default_factory=dict)  # cabinet berth id -> tuple[str]

    @property
    def has_water(self) -> bool:
        return self.device_type == "full"

    def outlets_for(self, berth_id: int) -> tuple:
        outs = self.berth_outlets.get(berth_id, ())
        if not self.has_water:
            outs = tuple(o for o in outs if o.startswith("Q"))
        return outs

    def berths_sharing(self, outlet: str, berth_id: int) -> list:
        return sorted(b for b, outs in self.berth_outlets.items()
                      if outlet in outs and b != berth_id)


def load(marina_id: int, db: Session) -> CabinetConfig:
    from ..models.berth import Berth, BerthOutlet
    from ..models.cabinet import Cabinet, Outlet

    cabinets = db.query(Cabinet).filter(Cabinet.marina_id == marina_id).all()
    if not cabinets:
        return CabinetConfig()
    # One cabinet server per marina in this model (marinas.pedestal_api_base_url);
    # if it ever holds both types, water is drawn only where a full cabinet is.
    types = {c.device_type for c in cabinets}
    device_type = "full" if "full" in types else "retrofit"

    mapping: dict = {}
    q = (db.query(Berth.cabinet_berth_id, Outlet.outlet_name)
         .join(BerthOutlet, BerthOutlet.berth_id == Berth.id)
         .join(Outlet, Outlet.id == BerthOutlet.outlet_id)
         .filter(Berth.marina_id == marina_id, Berth.cabinet_berth_id.isnot(None))
         .order_by(Outlet.outlet_name))
    for cab_berth, name in q:
        mapping.setdefault(cab_berth, []).append(name)
    return CabinetConfig(device_type=device_type,
                         berth_outlets={k: tuple(v) for k, v in mapping.items()})
