"""The demo marina in the ERP (D28, spec §6.11): one marina, 150 berths, 74 simulated
cabinets pointed at the demo simulator, reservations, and 30 days of history.

The layout and every value come from simulator/demo_world.py — the same module the
simulator serves from — so the ERP's history and the simulator's live answers are
one continuous series: the backfill ends at the moment of seeding, with the meter
state set there, and the collector carries on from it.

The two REAL cabinets (Krk, marina-iot) are not created here: their berths exist,
unlinked, and stay grey until 5d connects them.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from simulator import demo_world as w
from simulator.demo_sim import DEFAULT_PORT, DEFAULT_SEED, SERVICE_EMAIL

from ..models.berth import Berth, BerthReservation
from ..models.billing import Customer
from ..models.cabinet import Cabinet, Outlet
from ..models.marina import Marina
from ..models.metering import ConsumptionInterval, OutletMeterState
from ..services import cabinets as svc
from ..utils.time import utcnow

DEMO_MARINA = "Demo Marina"
AUTHOR = "demo-seed"
HISTORY_DAYS = 30


class DemoExists(Exception):
    pass


def sim_url(port: int, display_id: str) -> str:
    return f"http://127.0.0.1:{port}/c/{display_id}"


def find(db: Session) -> Optional[Marina]:
    return db.query(Marina).filter(Marina.name == DEMO_MARINA).first()


def seed(db: Session, *, port: int = DEFAULT_PORT, seed_value: int = DEFAULT_SEED,
         password: str = "demo-sim-local", days: int = HISTORY_DAYS,
         now: Optional[datetime] = None) -> dict:
    if find(db) is not None:
        raise DemoExists(f"'{DEMO_MARINA}' already exists — remove it first")
    now = (now or utcnow()).replace(microsecond=0)
    specs = w.cabinets()
    marina = Marina(name=DEMO_MARINA, location="Demo", timezone="Europe/Zagreb",
                    pedestal_api_base_url=sim_url(port, specs[0].display_id), status="active")
    db.add(marina)
    db.commit()

    # berths: all 150, in the drawing's order; linked below where a cabinet is simulated
    rows = {}
    for b in w.berths():
        row = Berth(marina_id=marina.id, berth_number=b.number, svg_id=b.svg_id,
                    length_m=Decimal(str(b.length_m)) if b.length_m is not None else None)
        db.add(row)
        rows[b.number] = row
    db.commit()

    for spec in specs:
        cab = svc.provision_cabinet(
            db, marina_id=marina.id, pedestal_pk=1, display_id=spec.display_id,
            device_type=spec.kind, base_url=sim_url(port, spec.display_id),
            service_email=SERVICE_EMAIL, service_password=password, dock=spec.zone,
            is_simulated=True)
        for slot, b in enumerate(spec.berths, start=1):
            berth = rows[b.number]
            berth.cabinet_id, berth.cabinet_berth_id = cab.id, slot
            db.commit()
            svc.set_berth_outlets(db, berth, list(spec.outlets_for(slot)), assigned_by=AUTHOR)

    n_res = _reservations(db, rows, seed_value, now)
    n_iv = _history(db, marina.id, seed_value, now, days)
    db.add(Customer(marina_id=marina.id, full_name="Demo guest", external_ref="demo-guest",
                    is_demo=True))
    db.commit()
    return {"marina_id": marina.id, "berths": len(rows), "cabinets": len(specs),
            "reservations": n_res, "intervals": n_iv, "history_days": days}


def _reservations(db, rows, seed_value, now) -> int:
    """A reservation where the world says the berth is reserved AND empty that day,
    from 30 days back to 7 days ahead; each lasts one day, midday to midday (UTC)."""
    n = 0
    today = w.day_of(now)
    for d in range(today - HISTORY_DAYS, today + 8):
        start = w.EPOCH + w.DAY_TURN + timedelta(days=d)
        empty = set(rows) - w.occupied_set(seed_value, d)
        for number in sorted(empty):
            if w.reserved(seed_value, number, d):
                db.add(BerthReservation(berth_id=rows[number].id, starts_at=start,
                                        ends_at=start + timedelta(days=1),
                                        note="demo", created_by=AUTHOR))
                n += 1
    db.commit()
    return n


def _history(db, marina_id, seed_value, now, days) -> int:
    """Hourly register differences per simulated socket, as the collector would have
    stored them (a run of idle hours is ONE zero row), then the meter state at `now`."""
    by_number = {b.number: b for b in w.berths()}
    start = (now - timedelta(days=days)).replace(minute=0, second=0)
    n = 0
    for spec in w.cabinets():
        cab = db.query(Cabinet).filter(Cabinet.marina_id == marina_id,
                                       Cabinet.display_id == spec.display_id).one()
        for slot, b in enumerate(spec.berths, start=1):
            socket = next(o for o in spec.outlets_for(slot) if o.startswith("Q"))
            out = db.query(Outlet).filter(Outlet.cabinet_id == cab.id,
                                          Outlet.outlet_name == socket).one()
            berth = by_number[b.number]
            prev_t, prev_e, last = start, w.register_kwh(seed_value, berth, start), None
            t = start
            while t < now:
                t_next = min(t + timedelta(hours=1), now)
                e = w.register_kwh(seed_value, berth, t_next)
                delta = Decimal(str(round(e - prev_e, 4)))
                if delta == 0 and last is not None and last.energy_kwh == 0:
                    last.to_at, last.meter_to = t_next, Decimal(str(e))
                else:
                    last = ConsumptionInterval(outlet_id=out.id, standalone=False,
                                               from_at=prev_t, to_at=t_next, energy_kwh=delta,
                                               meter_from=Decimal(str(prev_e)),
                                               meter_to=Decimal(str(e)), source="register")
                    db.add(last)
                    n += 1
                prev_t, prev_e, t = t_next, e, t_next
            db.flush()
            db.add(OutletMeterState(outlet_id=out.id, energy_kwh=Decimal(str(prev_e)),
                                    read_at=now, last_interval_id=last.id if last else None))
        db.commit()
    return n


def remove(db: Session) -> bool:
    """Delete the demo marina and everything under it. Real cabinets are never in it."""
    from ..models.berth import BerthOutlet, BerthOutletCabinet, MappingComparison, OutletNfcTag
    from ..models.cabinet import CabinetCapability
    from ..models.cache import AlarmLog, PedestalCache, SyncLog
    from ..models.metering import (CommandAudit, ConsumptionMonthly, ErpSession,
                                   ReconciliationRun)
    from ..models.security import ServiceWindow

    m = find(db)
    if m is None:
        return False
    cabs = [c.id for c in db.query(Cabinet.id).filter(Cabinet.marina_id == m.id)]
    if db.query(Cabinet).filter(Cabinet.id.in_(cabs), Cabinet.is_simulated.is_(False)).count():
        raise RuntimeError("the demo marina holds a REAL cabinet — remove it by hand first")
    berths = [b.id for b in db.query(Berth.id).filter(Berth.marina_id == m.id)]
    outs = [o.id for o in db.query(Outlet.id).filter(Outlet.cabinet_id.in_(cabs))]
    for model, col, ids in (
            (ConsumptionInterval, ConsumptionInterval.outlet_id, outs),
            (OutletMeterState, OutletMeterState.outlet_id, outs),
            (ConsumptionMonthly, ConsumptionMonthly.outlet_id, outs),
            (OutletNfcTag, OutletNfcTag.outlet_id, outs),
            (BerthOutlet, BerthOutlet.berth_id, berths),
            (BerthReservation, BerthReservation.berth_id, berths)):
        db.query(model).filter(col.in_(ids)).delete(synchronize_session=False)
    for model in (ErpSession, CommandAudit, ReconciliationRun, AlarmLog, CabinetCapability,
                  MappingComparison, BerthOutletCabinet, ServiceWindow):
        db.query(model).filter(model.cabinet_id.in_(cabs)).delete(synchronize_session=False)
    db.query(Berth).filter(Berth.id.in_(berths)).delete(synchronize_session=False)
    db.query(Outlet).filter(Outlet.id.in_(outs)).delete(synchronize_session=False)
    db.query(Cabinet).filter(Cabinet.id.in_(cabs)).delete(synchronize_session=False)
    for model in (PedestalCache, SyncLog, AlarmLog):
        db.query(model).filter(model.marina_id == m.id).delete(synchronize_session=False)
    db.query(Customer).filter(Customer.marina_id == m.id, Customer.is_demo.is_(True)).delete(
        synchronize_session=False)
    db.delete(m)
    db.commit()
    return True
