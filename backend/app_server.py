"""Unified agent-as-app server exposing REST + websocket endpoints."""
from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Any
from flask import Flask, send_from_directory
from flask_socketio import SocketIO
from .agent_app.api import api
from .agent_app.app_state import agent_state

logger = logging.getLogger(__name__)

def create_app() -> Flask:
    app = Flask(__name__, static_folder='../../frontend/dashboard', static_url_path='')
    socketio = SocketIO(app, cors_allowed_origins="*")
    
    # Register API blueprint
    app.register_blueprint(api)
    
    # Serve static dashboard files
    @app.get("/")
    def serve_dashboard() -> Any:
        return send_from_directory(app.static_folder, 'index.html')
    
    @app.get("/api/ping")
    def ping() -> Any:
        return {"status": "ok", "state": agent_state().health().last_updated}
    
    # WebSocket connection handler
    @socketio.on('connect')
    def handle_connect() -> None:
        logger.info("Client connected")
        return {"status": "connected"}
    
    @socketio.on('disconnect')
    def handle_disconnect() -> None:
        logger.info("Client disconnected")
    
    @socketio.on('message')
    def handle_message(data: Any) -> None:
        logger.info(f"Received message: {data}")
        socketio.emit('response', {'data': data})
    
    return app, socketio

def main() -> None:
    logging.basicConfig(level=logging.INFO)
    app, socketio = create_app()
    host = os.getenv("VAMP_AGENT_HOST", "0.0.0.0")
    port = int(os.getenv("VAMP_AGENT_PORT", "8080"))
    logger.info("Starting VAMP agent-as-app server on %s:%s", host, port)
    socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)

if __name__ == "__main__": # pragma: no cover
    main()
