"""What the ERP knows about a cabinet that the cabinet does not say (phase 2, interim).

The cabinet API does not tell:
  - whether it has water at all: valves/config and /water ALWAYS list two
    valves, also on a retrofit cabinet (Cloud_IOT a709cf8,
    pedestal_config.py:551-572, ext_pedestal_endpoints.py:325-377);
  - which outlets serve which berth: berth->outlet mapping is not exposed
    through /api/ext (NALAZ 4.2).

So both are ERP data (spec §4.1 `cabinets.device_type`, §4.2/§4.3 mapping).
Until phase 3 creates those tables, they come from one JSON file named by
ERP_CABINETS_FILE. Without the file nothing is guessed: water is not drawn,
and the power signal of a berth is UNKNOWN.

File shape:
  {"marinas": {"<marina_id>": {
      "device_type": "full" | "retrofit",
      "berths": {"<cabinet berth id>": ["Q1", "V1"], ...}}}}
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

_OUTLET = re.compile(r"^(Q[1-4]|V[1-2])$")


@dataclass(frozen=True)
class CabinetConfig:
    device_type: Optional[str] = None                 # None = not configured
    berth_outlets: dict = field(default_factory=dict)  # berth_id(int) -> tuple[str]

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


class CabinetConfigError(ValueError):
    pass


def parse(raw: dict, marina_id: int) -> CabinetConfig:
    m = (raw.get("marinas") or {}).get(str(marina_id))
    if m is None:
        return CabinetConfig()
    dt = m.get("device_type")
    if dt not in ("full", "retrofit"):
        raise CabinetConfigError(f"marina {marina_id}: device_type must be full|retrofit, got {dt!r}")
    berths = {}
    for bid, outs in (m.get("berths") or {}).items():
        bad = [o for o in outs if not _OUTLET.match(str(o))]
        if bad:
            raise CabinetConfigError(f"marina {marina_id} berth {bid}: bad outlet names {bad}")
        if dt == "retrofit" and any(o.startswith("V") for o in outs):
            raise CabinetConfigError(f"marina {marina_id} berth {bid}: retrofit has no water")
        berths[int(bid)] = tuple(outs)
    return CabinetConfig(device_type=dt, berth_outlets=berths)


def load(marina_id: int) -> CabinetConfig:
    path = os.environ.get("ERP_CABINETS_FILE")
    if not path:
        return CabinetConfig()
    try:
        with open(path, encoding="utf-8") as f:
            return parse(json.load(f), marina_id)
    except (OSError, json.JSONDecodeError, CabinetConfigError) as exc:
        # A broken file must be loud, and must not invent capabilities.
        log.error("[cabinet-config] %s unusable: %s", path, exc)
        return CabinetConfig()
