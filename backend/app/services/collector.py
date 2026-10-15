"""The collector: polls the cabinets on the §5.2 schedule, reconciles, runs retention.

D7: the poller and retention live in the same commit — app/services/retention.py
runs from here, daily. Nothing here is a "nice to have" for the webhook: the
webhook has no retry and no signature, so a missed event is gone; the pull is
what the money rests on.

Schedule (spec §5.2), per cabinet server or per cabinet:

  pedestals.health        60 s   server   -> cabinets.smart_mode, last_heartbeat_at
  sessions.active         60 s   server   -> cache (display), "is anything running"
  load.pedestal_get_ext   60 s   cabinet  -> register readings -> consumption_intervals
                         300 s            ... when nothing runs on the cabinet
  pedestals.status_ext   120 s   cabinet  -> cache (door_state, D16)
  alarms.active          120 s   server   -> alarm_log, once per cabinet alarm
  berths.list            300 s   server   -> cache (vessel signal, §3)
  reconcile              900 s   cabinet  -> sessions (reconciler.py)
  reconcile, nightly      02:00 UTC        -> the wide pass
  retention               daily

Intervals and D19: a register difference is stored per outlet. It is attributed
to an ERP session only when the cabinet was in Smart Mode ON and an ERP session
was active on that outlet; in Smart Mode OFF it is stored standalone, with no
session — shown, never billed. A zero difference extends the previous zero
interval instead of adding a row: an idle outlet is one row, not 288 a day.

One process collects. On PostgreSQL the collector takes an advisory lock and a
second process stays on standby; SQLite is single-process by nature.

It runs on ITS OWN thread and event loop (CollectorThread): its database work is
synchronous, and a cabinet can take seconds to answer — neither may ever make an
operator's request wait.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..cabinet.client import CabinetClient
from ..database import SessionLocal, engine
from ..models.cabinet import Cabinet, Outlet
from ..models.cache import AlarmLog
from ..models.metering import ConsumptionInterval, ErpSession, OutletMeterState
from ..utils.time import parse_utc, utcnow
from . import reconciler, retention
from .pedestal_api_factory import PedestalAPIClientFactory, get_pedestal_factory

log = logging.getLogger(__name__)

EVERY = {
    "health": 60, "sessions": 60, "load_active": 60, "load_idle": 300, "status": 120,
    "alarms": 120, "berths": 300, "reconcile": 900, "retention": 86400,
}
NIGHTLY_HOUR_UTC = 2
LEADER_LOCK_ID = 0x45525049   # 'ERPI'
TICK_SECONDS = 5
# Cabinet servers polled at once (6.0, D28): one dead server waits out its timeouts
# (3 attempts x 10 s) without holding up the others. Each server gets its own
# database session. SQLite stays at 1: a session there that changed rows before an
# await would hold the file's write lock, and the next server, on the same thread,
# would wait for it — PostgreSQL locks rows, not the database.
PARALLEL_SERVERS = 8


@dataclass
class Status:
    enabled: bool = False
    running: bool = False
    role: str = "stopped"            # stopped | leader | standby
    cycles: int = 0
    last_tick_at: Optional[datetime] = None
    last_error: Optional[str] = None
    counts: dict = field(default_factory=dict)

    def public(self) -> dict:
        return {"enabled": self.enabled, "running": self.running, "role": self.role,
                "cycles": self.cycles,
                "last_tick_at": self.last_tick_at.isoformat() + "Z" if self.last_tick_at else None,
                "last_error": self.last_error}


def _dec(v, places="0.0001") -> Optional[Decimal]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return Decimal(str(v)).quantize(Decimal(places))
    except Exception:  # noqa: BLE001 — a non-number register is "no reading", not a crash
        return None


def record_reading(db: Session, cab: Cabinet, outlet: Outlet, register_kwh: Decimal,
                   at: datetime) -> str:
    """One register reading -> at most one new interval row. Does not commit."""
    st = db.get(OutletMeterState, outlet.id)
    if st is None:
        db.add(OutletMeterState(outlet_id=outlet.id, energy_kwh=register_kwh, read_at=at))
        return "seeded"
    if at <= st.read_at:
        return "not_newer"
    prev_reg = Decimal(st.energy_kwh) if st.energy_kwh is not None else None
    if prev_reg is None or register_kwh < prev_reg:
        # a meter swap or reset: never a negative interval, never a guess (D10)
        log.warning("[collector] %s/%s register went %s -> %s; restarting from here",
                    cab.display_id, outlet.outlet_name, prev_reg, register_kwh)
        st.energy_kwh, st.read_at, st.last_interval_id = register_kwh, at, None
        return "reset"
    delta = register_kwh - prev_reg
    standalone = cab.smart_mode is False
    session_id = None
    if cab.smart_mode is True:
        s = (db.query(ErpSession.id)
             .filter(ErpSession.outlet_id == outlet.id, ErpSession.status == "active")
             .order_by(ErpSession.id.desc()).first())
        session_id = s[0] if s else None
    prev = db.get(ConsumptionInterval, st.last_interval_id) if st.last_interval_id else None
    if (delta == 0 and prev is not None and prev.energy_kwh is not None
            and Decimal(prev.energy_kwh) == 0 and prev.session_id == session_id
            and bool(prev.standalone) == standalone and prev.to_at == st.read_at):
        prev.to_at, prev.meter_to = at, register_kwh
        result = "extended"
    else:
        iv = ConsumptionInterval(outlet_id=outlet.id, session_id=session_id,
                                 standalone=standalone, from_at=st.read_at, to_at=at,
                                 energy_kwh=delta, meter_from=prev_reg, meter_to=register_kwh,
                                 source="register")
        db.add(iv)
        db.flush()
        st.last_interval_id = iv.id
        result = "interval"
    st.energy_kwh, st.read_at = register_kwh, at
    return result


class Collector:
    def __init__(self, factory: Optional[PedestalAPIClientFactory] = None,
                 session_factory=SessionLocal, transport=None, sleep=None,
                 parallel: Optional[int] = None):
        self.factory = factory or get_pedestal_factory()
        if transport is not None:
            self.factory.transport = transport
        if sleep is not None:
            self.factory.sleep = sleep
        self.session_factory = session_factory
        self._last: dict = {}           # task key -> when it last ran
        # cabinet id -> something runs on it; two sources, each overwritten on every read
        self._busy_sessions: dict = {}  # sessions.active lists it
        self._busy_load: dict = {}      # its last load reading showed power or current
        self._last_nightly: Optional[datetime] = None
        self.status = Status()
        self.parallel = parallel or (PARALLEL_SERVERS if engine.dialect.name == "postgresql"
                                     else 1)

    # ── scheduling ───────────────────────────────────────────────────────────

    def _is_due(self, key: tuple, every: int, now: datetime) -> bool:
        # measured from the LAST run, not scheduled ahead: a cabinet that just got busy
        # moves to the 60 s cadence at once instead of serving out an idle 300 s
        last = self._last.get(key)
        if last is not None and (now - last).total_seconds() < every:
            return False
        self._last[key] = now
        return True

    async def run_all_once(self) -> dict:
        """Everything, now — tests and the growth check use this."""
        self._last.clear()
        return await self.tick(force_nightly=False)

    async def tick(self, force_nightly: bool = False) -> dict:
        now = utcnow()
        counts: dict = {}
        db = self.session_factory()
        try:
            servers: dict = {}
            for cid, url, email in (db.query(Cabinet.id, Cabinet.base_url, Cabinet.service_email)
                                    .order_by(Cabinet.id)):
                servers.setdefault((url, email), []).append(cid)
        finally:
            db.close()
        nightly = force_nightly or self._nightly_due(now)
        gate = asyncio.Semaphore(self.parallel)

        async def one_server(base_url: str, ids: list) -> dict:
            async with gate:
                local: dict = {}
                sdb = self.session_factory()     # never shared between servers
                try:
                    cabs = sdb.query(Cabinet).filter(Cabinet.id.in_(ids)).order_by(Cabinet.id).all()
                    try:
                        client = self.factory.for_cabinet(cabs[0])
                    except ValueError as exc:
                        self.status.last_error = str(exc)
                        return local
                    await self._server_tasks(sdb, base_url, cabs, client, now, local)
                    for cab in cabs:
                        await self._cabinet_tasks(sdb, cab, self.factory.for_cabinet(cab), now,
                                                  local, nightly)
                except Exception as exc:  # noqa: BLE001 — one bad server never stops the rest
                    log.exception("[collector] server %s failed", base_url)
                    self.status.last_error = f"{base_url}: {type(exc).__name__}: {exc}"[:500]
                finally:
                    sdb.close()
                return local

        for local in await asyncio.gather(*(one_server(url, ids)
                                            for (url, _email), ids in servers.items())):
            for k, v in local.items():
                counts[k] = counts.get(k, 0) + v
        if self._is_due(("retention",), EVERY["retention"], now):
            db = self.session_factory()
            try:
                counts["retention"] = retention.run(db, now)
            finally:
                db.close()
        self.status.cycles += 1
        self.status.last_tick_at = now
        self.status.counts = counts
        return counts

    def _nightly_due(self, now: datetime) -> bool:
        if now.hour != NIGHTLY_HOUR_UTC:
            return False
        if self._last_nightly and self._last_nightly.date() == now.date():
            return False
        self._last_nightly = now
        return True

    # ── tasks ────────────────────────────────────────────────────────────────

    async def _server_tasks(self, db, base_url, cabs, client: CabinetClient, now, counts):
        if self._is_due(("health", base_url), EVERY["health"], now):
            out = await client.health(db)
            if out.ok and isinstance(out.data, dict):
                for cab in cabs:
                    h = out.data.get(str(cab.pedestal_pk))
                    if not isinstance(h, dict):
                        continue
                    cab.smart_mode = h.get("smart_mode") if isinstance(
                        h.get("smart_mode"), bool) else None
                    cab.last_heartbeat_at = parse_utc(h.get("last_heartbeat"))
                    cab.last_polled_at = now
                db.commit()
            counts["health"] = counts.get("health", 0) + 1
        if self._is_due(("sessions", base_url), EVERY["sessions"], now):
            out = await client.active_sessions(db)
            if out.ok and isinstance(out.data, list):
                running = {r.get("pedestal_id") for r in out.data if isinstance(r, dict)}
                for cab in cabs:
                    self._busy_sessions[cab.id] = cab.pedestal_pk in running
            counts["sessions"] = counts.get("sessions", 0) + 1
        if self._is_due(("alarms", base_url), EVERY["alarms"], now):
            out = await client.active_alarms(db)
            if out.ok and isinstance(out.data, list):
                counts["alarms_new"] = counts.get("alarms_new", 0) + \
                    self._store_alarms(db, cabs, out.data, now)
        if self._is_due(("berths", base_url), EVERY["berths"], now):
            await client.list_berths(db)

    def _store_alarms(self, db, cabs, alarms: list, now) -> int:
        by_pk = {c.pedestal_pk: c for c in cabs}
        new = 0
        for a in alarms:
            if not isinstance(a, dict) or not isinstance(a.get("id"), int):
                continue
            cab = by_pk.get(a.get("pedestal_id"))
            if cab is None:
                continue
            exists = (db.query(AlarmLog.id).filter(AlarmLog.cabinet_id == cab.id,
                                                   AlarmLog.cabinet_alarm_id == a["id"]).first())
            if exists:
                continue
            db.add(AlarmLog(marina_id=cab.marina_id, pedestal_id=cab.pedestal_pk, alarm_data=a,
                            received_at=now, cabinet_id=cab.id, cabinet_alarm_id=a["id"],
                            source="poll"))
            try:
                db.commit()
                new += 1
            except IntegrityError:
                db.rollback()       # the webhook stored it a moment ago
        return new

    async def _cabinet_tasks(self, db, cab, client, now, counts, nightly):
        busy = (self._busy_sessions.get(cab.id) or self._busy_load.get(cab.id)
                or self._erp_session_open(db, cab))
        every = EVERY["load_active"] if busy else EVERY["load_idle"]
        if cab.is_simulated:
            # D28: 74 demo cabinets at the 60 s cadence were ~115 000 interval rows a
            # day (measured); a demo needs a five-minute picture, not a meter record
            every = EVERY["load_idle"]
        if self._is_due(("load", cab.id), every, now):
            out = await client.pedestal_load(cab.pedestal_pk, db)
            if out.ok and isinstance(out.data, dict):
                n = self._store_load(db, cab, out.data.get("sockets") or [], now)
                for k, v in n.items():
                    counts[k] = counts.get(k, 0) + v
        if self._is_due(("status", cab.id), EVERY["status"], now):
            await client.pedestal_status(cab.pedestal_pk, db)
        if cab.is_simulated:
            return          # D28: no channel B, no NFC sessions — nothing to reconcile
        if nightly or self._is_due(("reconcile", cab.id), EVERY["reconcile"], now):
            run = await reconciler.reconcile(db, cab, client, now, nightly=nightly)
            counts["reconcile_runs"] = counts.get("reconcile_runs", 0) + 1
            if not run.ok:
                self.status.last_error = f"{cab.display_id}: {run.error}"

    def _erp_session_open(self, db, cab) -> bool:
        return db.query(ErpSession.id).filter(
            ErpSession.cabinet_id == cab.id,
            ErpSession.status.in_(("reserved", "active"))).first() is not None

    def _store_load(self, db, cab, sockets: list, now) -> dict:
        outlets = {o.outlet_name: o for o in
                   db.query(Outlet).filter(Outlet.cabinet_id == cab.id)}
        counts: dict = {}
        busy = False
        for sk in sockets:
            if not isinstance(sk, dict) or not isinstance(sk.get("socket_id"), int):
                continue
            outlet = outlets.get(f"Q{sk['socket_id']}")   # load.* is sockets only
            reg = _dec(sk.get("energy_kwh"))
            if outlet is None or reg is None:
                continue
            if (sk.get("power_kw") or 0) > 0 or (sk.get("current_amps") or 0) > 0:
                busy = True
            r = record_reading(db, cab, outlet, reg, now)
            counts[f"readings_{r}"] = counts.get(f"readings_{r}", 0) + 1
        db.commit()
        self._busy_load[cab.id] = busy
        return counts

    # ── the loop ─────────────────────────────────────────────────────────────

    async def run_forever(self, stop: asyncio.Event) -> None:
        self.status.enabled = self.status.running = True
        leader = None
        try:
            while not stop.is_set():
                if leader is None:
                    leader = self._take_leadership()
                    self.status.role = "leader" if leader is not None else "standby"
                if leader is not None:
                    try:
                        await self.tick()
                    except Exception as exc:  # noqa: BLE001 — the loop must outlive one bad tick
                        log.exception("[collector] tick failed")
                        self.status.last_error = f"{type(exc).__name__}: {exc}"[:500]
                try:
                    await asyncio.wait_for(stop.wait(),
                                           timeout=TICK_SECONDS if leader is not None else 60)
                except asyncio.TimeoutError:
                    pass
        finally:
            self.status.running = False
            self.status.role = "stopped"
            if leader is not None and leader is not True:
                leader.close()

    def _take_leadership(self):
        """PostgreSQL: an advisory lock held on its own connection. SQLite: one process."""
        if engine.dialect.name != "postgresql":
            return True
        conn = engine.connect()
        got = conn.execute(text("SELECT pg_try_advisory_lock(:k)"),
                           {"k": LEADER_LOCK_ID}).scalar()
        if got:
            conn.commit()
            return conn
        conn.close()
        return None


class CollectorThread:
    """The collector on a thread of its own, with its own event loop."""

    def __init__(self, col: Collector):
        self.col = col
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop: Optional[asyncio.Event] = None
        self._ready = threading.Event()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="collector", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=10)

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop, self._stop = loop, asyncio.Event()
        self._ready.set()
        try:
            loop.run_until_complete(self.col.run_forever(self._stop))
        finally:
            loop.close()

    def stop(self, timeout: float = 30) -> None:
        if self._loop is not None and self._stop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._stop.set)
        if self._thread is not None:
            self._thread.join(timeout)


collector = Collector()
