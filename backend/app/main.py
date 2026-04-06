"""ERP-IOT FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db
from .middleware.security import SecurityMiddleware
from .services.websocket_manager import ws_manager
from .routers import auth, marinas, dashboard, controls, energy, alarms, webhooks
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
    yield
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
app.include_router(webhooks.router)


# ── Health endpoint ───────────────────────────────────────────────────────────
@app.get("/api/health", tags=["system"])
def health():
    return {
        "status": "ok",
        "service": "erp-iot",
        "version": "1.0.0",
        "ws_connections": ws_manager.connection_count,
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

    Authentication: pass token=<JWT> query param.
    """
    # Optional auth check
    if token:
        payload = _decode_token(token)
        if not payload:
            await websocket.close(code=4001)
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
