"""Legacy plain WebSocket bridge that reuses the Socket.IO action handlers."""
from __future__ import annotations

"""
Legacy plain WebSocket bridge.

The Chrome extension and dashboard now speak Socket.IO to
``backend.app_server`` on port 8080. This module is retained only as an
optional compatibility shim for older dashboards or debugging scenarios.
Enable it via ``START_WS_BRIDGE=1`` when running ``scripts/setup_backend.bat``;
it is not part of the default startup path.
"""

import asyncio
import json
from typing import Any, Dict

import websockets
from websockets.server import WebSocketServerProtocol

from .agent_app.ws_dispatcher import WSActionDispatcher, _fail
from .logging_utils import configure_quiet_logger
from .settings import APP_HOST, APP_PORT

logger = configure_quiet_logger(
    __name__, env_level_var="VAMP_WS_LOG_LEVEL", default_console_level="INFO", file_name="ws_bridge.log"
)


class _WebSocketAdapter:
    """Adapter that mimics the minimal Socket.IO surface used by ``WSActionDispatcher``."""

    def __init__(self, websocket: WebSocketServerProtocol) -> None:
        self.websocket = websocket

    def emit(self, event: str, data: Dict[str, Any], to: str | None = None) -> None:
        message = data if event == "response" else {"event": event, "data": data}
        asyncio.create_task(self.websocket.send(json.dumps(message)))

    def start_background_task(self, target, *args, **kwargs):  # type: ignore[override]
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(None, target, *args, **kwargs)


async def _handle_connection(websocket: WebSocketServerProtocol, path: str) -> None:
    sid = f"ws-{id(websocket)}"
    adapter = _WebSocketAdapter(websocket)
    dispatcher = WSActionDispatcher(adapter)
    logger.info("Client connected: sid=%s ip=%s path=%s", sid, websocket.remote_address, path)
    try:
        async for raw in websocket:
            try:
                payload: Any = json.loads(raw)
            except json.JSONDecodeError:
                logger.info("Invalid JSON from %s: %s", sid, raw)
                await websocket.send(json.dumps(_fail("ERROR", "invalid_json")))
                continue

            logger.info("Received action from %s: %s", sid, payload)
            dispatcher.dispatch(sid, payload)
    except websockets.ConnectionClosedError:
        logger.info("Client disconnected: sid=%s", sid)
    finally:
        dispatcher.forget_session(sid)


def main() -> None:  # pragma: no cover
    logger.info("Starting legacy WebSocket bridge on %s:%s", APP_HOST, APP_PORT)
    loop = asyncio.get_event_loop()
    server = websockets.serve(_handle_connection, APP_HOST, APP_PORT)
    loop.run_until_complete(server)
    loop.run_forever()


if __name__ == "__main__":  # pragma: no cover
    main()
