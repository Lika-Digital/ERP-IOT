"""WebSocket connection manager — adapted from Pedestal SW pattern."""
import asyncio
import json
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)

_SEND_TIMEOUT = 5.0


class WebSocketManager:
    def __init__(self):
        # List of (websocket, marina_id | None)
        self._connections: list[tuple[WebSocket, int | None]] = []

    async def connect(self, websocket: WebSocket, marina_id: int | None = None):
        await websocket.accept()
        self._connections.append((websocket, marina_id))
        logger.info(
            f"WebSocket connected (marina_id={marina_id}). "
            f"Total: {len(self._connections)}"
        )

    def disconnect(self, websocket: WebSocket):
        self._connections = [
            (ws, mid) for ws, mid in self._connections if ws is not websocket
        ]
        logger.info(f"WebSocket disconnected. Total: {len(self._connections)}")

    async def broadcast(self, message: dict):
        """Send to all connected clients."""
        data = json.dumps(message)
        dead: list[WebSocket] = []
        for ws, _ in self._connections:
            try:
                await asyncio.wait_for(ws.send_text(data), timeout=_SEND_TIMEOUT)
            except asyncio.TimeoutError:
                logger.warning("WebSocket send timed out — dropping stale connection")
                dead.append(ws)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def broadcast_to_marina(self, marina_id: int, message: dict):
        """Send only to clients subscribed to a specific marina."""
        data = json.dumps(message)
        dead: list[WebSocket] = []
        for ws, mid in self._connections:
            # Send if client is subscribed to this marina or has no filter
            if mid is None or mid == marina_id:
                try:
                    await asyncio.wait_for(ws.send_text(data), timeout=_SEND_TIMEOUT)
                except asyncio.TimeoutError:
                    logger.warning("WebSocket send timed out — dropping stale connection")
                    dead.append(ws)
                except Exception:
                    dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


ws_manager = WebSocketManager()
