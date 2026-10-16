"""ERP-IOT FastAPI application entry point."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db
from .middleware.security import SecurityMiddleware
from .services.collector import CollectorThread, collector
from .services.websocket_manager import ws_manager
from .routers import (auth, berth_detail, marinas, dashboard, controls, energy, alarms, webhooks, pedestal_ext,
                      cabinet_admin, users, security)
from .routers.auth import _decode_token

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("ERP-IOT starting up...")
    init_db()
    worker = None
    if settings.collector_enabled:
        # spec §5.2: an ERP that does not collect is broken, so it starts with the app —
        # on its own thread, so no operator request ever waits on it (§4.0b)
        worker = CollectorThread(collector)
        worker.start()
    else:
        log.warning("COLLECTOR_ENABLED is false: nothing is collected from the cabinets")
    yield
    if worker is not None:
        await asyncio.to_thread(worker.stop)
    log.info("ERP-IOT shutting down.")


app = FastAPI(
    title="ERP-IOT",
    description="Central ERP layer for multi-marina pedestal management",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Security middleware ────────────────────────────────────────────────────────
app.add_middleware(SecurityMiddleware)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(marinas.router)
app.include_router(dashboard.router)
app.include_router(controls.router)
app.include_router(energy.router)
app.include_router(alarms.router)
app.include_router(pedestal_ext.router)
app.include_router(webhooks.router)
app.include_router(cabinet_admin.router)
app.include_router(berth_detail.router)        # D27 phase 1, D30 (§6.10, §6.12)
app.include_router(users.router)
app.include_router(security.router)
app.include_router(security.decoy_router)   # layer 2: answers like a missing route


# ── Health endpoint ───────────────────────────────────────────────────────────
@app.get("/api/health", tags=["system"])
def health():
    return {
        "status": "ok",
        "service": "erp-iot",
        "version": "1.0.0",
        "ws_connections": ws_manager.connection_count,
        "collector": collector.status.public(),
    }


# ── WebSocket endpoint ────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(default=None),
    marina_id: int = Query(default=None),
):
    """
    WebSocket endpoint. Clients can subscribe to a specific marina by passing
    marina_id as a query param. Without marina_id they receive all broadcasts.

    Authentication: token=<JWT> query param — a FULL token (password and 2FA).
    Until D20 the token was optional and anyone reaching /ws got every broadcast.
    """
    payload = _decode_token(token) if token else None
    if not payload:
        await websocket.close(code=4001)
        return
    # A Marina Manager hears only an assigned marina, and must say which one:
    # without marina_id the manager would hear every marina's broadcasts (D20).
    if payload.get("role") != "admin" and (
            marina_id is None or marina_id not in (payload.get("marina_ids") or [])):
        await websocket.close(code=4003)
        return

    await ws_manager.connect(websocket, marina_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
