"""Quick Socket.IO sanity check for the VAMP WebSocket API."""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
from typing import Any, Dict

import socketio

DEFAULT_HOST = os.getenv("VAMP_AGENT_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("VAMP_AGENT_PORT", "8080"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", default="GET_STATE", help="Action to send (default: GET_STATE)")
    parser.add_argument("--host", default=DEFAULT_HOST, help="WebSocket host (default: %(default)s)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="WebSocket port (default: %(default)s)")
    parser.add_argument("--email", default="tester@example.com", help="Dummy email to include in payload")
    args = parser.parse_args()

    payload: Dict[str, Any] = {"action": args.action, "email": args.email}
    sio = socketio.Client(logger=False, engineio_logger=False)
    done = threading.Event()

    @sio.event
    def connect() -> None:  # pragma: no cover - developer helper
        print(f"Connected to ws://{args.host}:{args.port}/socket.io")
        sio.emit("message", payload)

    @sio.on("response")
    def on_response(data: Any) -> None:  # pragma: no cover - developer helper
        print("Received response:\n" + json.dumps(data, indent=2))
        done.set()

    @sio.event
    def disconnect() -> None:  # pragma: no cover - developer helper
        print("Disconnected")
        done.set()

    sio.connect(
        f"http://{args.host}:{args.port}",
        transports=["websocket"],
        socketio_path="socket.io",
        wait_timeout=5,
        headers={"User-Agent": "VAMP-ws-test"},
    )

    # Wait briefly for the response before closing.
    done.wait(timeout=5)
    time.sleep(0.2)
    sio.disconnect()


if __name__ == "__main__":  # pragma: no cover
    main()
