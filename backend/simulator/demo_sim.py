"""The demo marina's simulated cabinets, on ONE port (D28, spec §6.11).

    python -m simulator.demo_sim serve [--port 18080] [--seed 28]
    python -m simulator.demo_sim scenario offline SIM_C_04
    python -m simulator.demo_sim scenario wrong-vessel C-11
    python -m simulator.demo_sim scenario reset
    python -m simulator.demo_sim state

Each of the 74 simulated cabinets is the phase-2 simulator (cabinet_sim.py, the
same ext API and the same quirks) mounted under its own prefix:

    http://127.0.0.1:18080/c/SIM_C_04/api/ext/...

so to the ERP it is one cabinet server per cabinet, like the real ones. Before a
cabinet answers, its state is set from the world (demo_world.py) at that moment:
nothing here is remembered except the scenarios.

The server only ever ANSWERS: it holds no address of any real cabinet, and a
scenario names a simulated cabinet or berth or nothing. It listens on 127.0.0.1
only. The one client here is the command line, talking to this server on
127.0.0.1. The phase-2 test routes (/__sim/...) are closed on the demo cabinets:
only /__demo/ changes anything, and only the scenarios.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import demo_world as w
from .cabinet_sim import Socket, SimState, _berth, create_app, iso_z, make_state

DEFAULT_PORT = 18080
DEFAULT_SEED = 28
SERVICE_EMAIL = "erp@demo.sim"
OFFLINE_HEARTBEAT_S = 11 * 60          # older than the ERP's 10-minute OFFLINE threshold (D2)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DemoWorld:
    """The 74 cabinets' states, refreshed from the world, plus the scenarios."""

    def __init__(self, seed: int = DEFAULT_SEED, password: Optional[str] = None,
                 clock=_now):
        self.seed = seed
        self.password = password or os.environ.get("DEMO_SIM_PASSWORD", "demo-sim-local")
        self.clock = clock
        self.specs = {c.display_id: c for c in w.cabinets()}
        self.berth_cab = {b.number: c.display_id for c in self.specs.values() for b in c.berths}
        self.states: dict[str, SimState] = {}
        for cid, spec in self.specs.items():
            st = make_state("retrofit" if spec.kind == "retrofit" else "full")
            st.display_id, st.pk = cid, 1
            st.service_email, st.service_password = SERVICE_EMAIL, self.password
            st.erp_api_key = None                   # no channel B on a simulated cabinet
            self.states[cid] = st
        self.offline: dict[str, datetime] = {}       # cabinet -> when it went quiet
        self.wrong: set[str] = set()                 # berths forced to Wrong vessel

    # ── scenarios ────────────────────────────────────────────────────────────
    def scenario(self, name: str, target: Optional[str]) -> dict:
        if name == "reset":
            self.offline.clear()
            self.wrong.clear()
            return {"ok": True, "scenario": "reset"}
        if name == "offline":
            if target not in self.specs:
                return {"ok": False, "error": f"{target!r} is not a simulated cabinet"}
            self.offline.setdefault(target, self.clock())
            return {"ok": True, "scenario": name, "cabinet": target}
        if name == "wrong-vessel":
            if target not in self.berth_cab:
                return {"ok": False, "error": f"{target!r} is not a simulated berth"}
            self.wrong.add(target)
            return {"ok": True, "scenario": name, "berth": target}
        if name in ("ir-alarm", "unauthorised-access"):
            return {"ok": False, "error": f"{name} arrives with the Safety & Security "
                                          "devices (phase 6d)"}
        if name == "prepaid-zero":
            return {"ok": False, "error": "prepaid-zero needs the NFC flow (phase 7)"}
        return {"ok": False, "error": f"unknown scenario {name!r}"}

    def public(self) -> dict:
        return {"seed": self.seed, "cabinets": len(self.specs),
                "offline": sorted(self.offline), "wrong_vessel": sorted(self.wrong)}

    # ── one cabinet, now ─────────────────────────────────────────────────────
    def refresh(self, cid: str) -> SimState:
        st, spec, t = self.states[cid], self.specs[cid], self.clock()
        quiet = self.offline.get(cid)
        if quiet is not None:
            t = quiet                              # frozen: its last word is from then
        st.heartbeat_age_s = (self.clock() - quiet).total_seconds() + OFFLINE_HEARTBEAT_S \
            if quiet is not None else 5.0
        st.smart_mode = True
        st.clock = self.clock
        n_sockets = 4
        st.sockets = [Socket(i, 3 if (i == 1 and spec.kind == "full") else 1,
                             32.0 if (i <= 2 and spec.kind == "full") else 16.0)
                      for i in range(1, n_sockets + 1)]
        for sock in st.sockets:                    # spare sockets: idle, steady register
            sock.plug_inserted, sock.power_kw, sock.current = False, 0.0, 0.0
            sock.energy_kwh = round(500.0 + 100 * w.u(self.seed, "spare", cid, sock.socket_id), 4)
        st.berths, st.sessions, st.alarms = [], [], []
        for slot, b in enumerate(spec.berths, start=1):
            socket_name = next(o for o in spec.outlets_for(slot) if o.startswith("Q"))
            sock = st.sockets[int(socket_name[1]) - 1]
            kw = w.power_kw(self.seed, b, t)
            sock.energy_kwh = w.register_kwh(self.seed, b, t)
            sock.power_kw = kw
            sock.current = round(kw * 1000 / (230 * sock.phases), 2)
            sock.plug_inserted = w.plugged(self.seed, b.number, t)
            sock.display_state = "active" if kw > 0 else "idle"
            code = 0
            if w.occupied(self.seed, b.number, t):
                code = 2 if (b.number in self.wrong or w.wrong_vessel(self.seed, b.number, t)) else 1
            row = _berth(slot, b.number, 1, state_code=code)
            row["last_analyzed"] = iso_z(t - timedelta(minutes=2))
            st.berths.append(row)
            if kw > 0:
                st.sessions.append({
                    "id": int(w.u(self.seed, "sess", b.number, w.day_of(t)) * 1e9),
                    "pedestal_id": 1, "socket_id": sock.socket_id, "type": "electricity",
                    "status": "active", "started_at": None, "ended_at": None,
                    "energy_kwh": None, "water_liters": None, "customer_id": None,
                    "nfc_user_id": None, "deny_reason": None, "customer_name": None})
        kind = w.cabinet_alarm(self.seed, spec, t)
        st.moisture, st.temperature = 40.0, 21.5
        if kind is not None:
            if kind == "moisture":
                st.moisture = 95.0
            else:
                st.temperature = 58.0
            st.alarms = [{
                "id": int(w.u(self.seed, "alarm_id", cid, w.day_of(t)) * 1e9),
                "alarm_type": kind, "source": "mqtt", "pedestal_id": 1, "status": "triggered",
                "severity": None, "message": "Moisture above 90 %" if kind == "moisture"
                else "Temperature above 50", "details": None,
                "triggered_at": iso_z(t), "acknowledged_at": None, "acknowledged_by": None,
                "resolved_at": None}]
        # a long-running server must not grow: keep the last calls, drop dead tokens
        del st.calls[:-100]
        now = self.clock()
        st.tokens = {k: v for k, v in st.tokens.items() if v > now}
        return st


def create_demo_app(world: Optional[DemoWorld] = None) -> FastAPI:
    world = world or DemoWorld()
    app = FastAPI(title="demo marina simulator", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.world = world
    for cid, st in world.states.items():
        app.mount(f"/c/{cid}", create_app(st))

    @app.middleware("http")
    async def refresh(request: Request, call_next):
        parts = request.url.path.split("/")
        if len(parts) > 2 and parts[1] == "c" and parts[2] in world.states:
            if len(parts) > 3 and parts[3] == "__sim":
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            world.refresh(parts[2])
        return await call_next(request)

    @app.post("/__demo/scenario")
    async def scenario(request: Request):
        body = await request.json()
        out = world.scenario(body.get("name", ""), body.get("target"))
        return JSONResponse(out, status_code=200 if out["ok"] else 400)

    @app.get("/__demo/state")
    def state():
        return world.public()

    return app


def _post(port: int, path: str, body: Optional[dict] = None) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:  # noqa: S310 — 127.0.0.1 only
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="erp-sim", description=__doc__.split("\n")[0])
    p.add_argument("--port", type=int, default=int(os.environ.get("DEMO_SIM_PORT", DEFAULT_PORT)))
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--seed", type=int, default=int(os.environ.get("DEMO_SIM_SEED", DEFAULT_SEED)))
    sc = sub.add_parser("scenario")
    sc.add_argument("name", choices=("offline", "wrong-vessel", "ir-alarm", "unauthorised-access",
                                     "prepaid-zero", "reset"))
    sc.add_argument("target", nargs="?")
    sub.add_parser("state")
    a = p.parse_args(argv)
    if a.cmd == "serve":
        import uvicorn
        uvicorn.run(create_demo_app(DemoWorld(seed=a.seed)), host="127.0.0.1", port=a.port,
                    log_level="warning")
        return 0
    out = _post(a.port, "/__demo/scenario", {"name": a.name, "target": a.target}) \
        if a.cmd == "scenario" else _post(a.port, "/__demo/state")
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
