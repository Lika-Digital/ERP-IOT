"""Router side of the cabinet contract: get a client, turn an Outcome into a response.

One mapping from outcome code to ERP HTTP status, so no router invents its own
and no cabinet outcome ever becomes a 500 (spec §2.5, TC-ERP-SIM-06/07).
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..cabinet.client import CabinetClient
from ..cabinet.outcomes import Outcome
from ..models.marina import Marina
from ..models.user import User
from ..services.pedestal_api_factory import PedestalAPIClientFactory
from .auth import require_marina_access

# Commands: what the operator did was refused or could not be delivered.
COMMAND_HTTP = {
    "ok": 200,
    "already_ended": 200,          # staff closed it first; not an error (D10)
    "standalone": 409,
    "awaiting_plug": 409,
    "outlet_busy": 409,
    "nfc_mapping_mismatch": 409,
    "session_state_changed": 409,
    "conflict": 409,
    "not_found": 404,
    "not_enabled": 503,
    "capability_unavailable": 503,
    "no_contact": 503,
    "stale": 503,
    "cabinet_auth_failed": 503,
    "erp_bug": 502,                # our request was wrong; logged as a bug by the client
}


def marina_client(marina_id: int, user: User, db: Session,
                  factory: PedestalAPIClientFactory) -> tuple[Marina, CabinetClient]:
    marina = db.get(Marina, marina_id)
    if not marina:
        raise HTTPException(status_code=404, detail="Marina not found")
    require_marina_access(marina_id, user, db)
    try:
        return marina, factory.get_client(marina_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "cabinet_not_configured",
            "sentence": "Ormar ove marine nije podešen.",
            "endpoint": None, "is_stale": False, "data_as_of": None,
            "reason": str(exc),
        }) from exc


def read(outcome: Outcome, field: str, **extra) -> dict:
    """A read always answers 200: data (possibly stale or None) + the outcome."""
    return {field: outcome.data if outcome.has_data else None,
            "is_stale": outcome.is_stale, "outcome": outcome.public(), **extra}


def command(outcome: Outcome) -> dict:
    status = COMMAND_HTTP[outcome.code]
    if status != 200:
        raise HTTPException(status_code=status, detail=outcome.public())
    return {"ok": True, "outcome": outcome.public(), "result": outcome.data}
