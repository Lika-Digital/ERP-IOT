"""Dashboard router — aggregated marina overview data, and the berth view (spec §3, §6.2)."""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..cabinet import berth_view, cabinet_config
from ..database import get_db
from ..models.user import User
from ..models.cache import PedestalCache
from ..services.pedestal_api_factory import PedestalAPIClientFactory, get_pedestal_factory
from ._cabinet import marina_client, read
from .auth import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marinas", tags=["dashboard"])


@router.get("/{marina_id}/dashboard")
async def get_dashboard(
    marina_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """Pedestals, health, active and pending sessions. Every read carries its outcome."""
    marina, client = marina_client(marina_id, user, db, factory)
    pedestals = await client.list_pedestals(db)
    health = await client.health(db)
    active = await client.active_sessions(db)
    pending = await client.pending_sessions(db)
    outcomes = [pedestals, health, active, pending]

    # Webhook readings, keyed by the REAL pedestal id (API cache rows have none)
    cache_rows = (
        db.query(PedestalCache)
        .filter(PedestalCache.marina_id == marina_id, PedestalCache.pedestal_id.isnot(None))
        .all()
    )
    temperature_map = {
        row.pedestal_id: {
            "value": row.last_temperature,
            "alarm": row.last_temperature_alarm,
            "at": row.last_temperature_at.isoformat() if row.last_temperature_at else None,
        }
        for row in cache_rows
        if row.last_temperature is not None
    }
    readings_map = {row.pedestal_id: row.last_readings for row in cache_rows if row.last_readings}

    return {
        "marina_id": marina_id,
        "marina_name": marina.name,
        "is_stale": any(o.is_stale for o in outcomes),
        "pedestals": pedestals.data if pedestals.has_data else None,
        "health": health.data if health.has_data else None,
        "active_sessions": active.data if active.has_data else None,
        "pending_sessions": pending.data if pending.has_data else None,
        "outcomes": {o.endpoint_key: o.public() for o in outcomes},
        "temperature_map": temperature_map,
        "readings_map": readings_map,
    }


@router.get("/{marina_id}/health")
async def get_health(
    marina_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    _, client = marina_client(marina_id, user, db, factory)
    return read(await client.health(db), "data", marina_id=marina_id)


@router.get("/{marina_id}/pedestals")
async def list_pedestals(
    marina_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    _, client = marina_client(marina_id, user, db, factory)
    return read(await client.list_pedestals(db), "pedestals", marina_id=marina_id)


@router.get("/{marina_id}/berths")
async def list_berths(
    marina_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    factory: PedestalAPIClientFactory = Depends(get_pedestal_factory),
):
    """Berths with server-computed status, outlets, and controls only where they work.

    The frontend renders `berth_colour` and `status_sentence` and never derives a
    status itself (spec §3, TC-ERP-SIM-15).
    """
    _, client = marina_client(marina_id, user, db, factory)
    # sequential on purpose: one SQLAlchemy session must not be shared by
    # concurrently running coroutines (each call writes sync_log)
    health = await client.health(db)
    berths = await client.list_berths(db)

    pks = sorted(int(k) for k in (health.data or {}) if str(k).isdigit())         if health.has_data and isinstance(health.data, dict) else []
    status, load, breakers = {}, {}, {}
    for pk in pks:
        status[pk] = await client.pedestal_status(pk, db)
        load[pk] = await client.pedestal_load(pk, db)
        breakers[pk] = await client.pedestal_breakers(pk, db)
    alarms = await client.active_alarms(db)
    sessions = await client.active_sessions(db)

    # A control is offered only if the command endpoint is not known to be off.
    controls_enabled = not client.is_known_not_enabled("controls.socket_cmd")

    view = berth_view.build(
        health=health, berths=berths, status=status, load=load, breakers=breakers,
        alarms=alarms, sessions=sessions, config=cabinet_config.load(marina_id, db),
        controls_enabled=controls_enabled,
    )
    view["marina_id"] = marina_id
    return view
