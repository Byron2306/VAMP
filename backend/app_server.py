"""Unified agent-as-app server exposing REST + websocket endpoints."""
from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Any
from flask import Flask, request, send_from_directory
from flask_socketio import SocketIO
from .agent_app.api import api
from .agent_app.app_state import agent_state
from .agent_app.ws_dispatcher import WSActionDispatcher

logger = logging.getLogger(__name__)

def create_app() -> tuple:
    # Calculate path to dashboard folder
    backend_dir = Path(__file__).parent
    dashboard_dir = backend_dir.parent / 'frontend' / 'dashboard'
    
    app = Flask(__name__, static_folder=str(dashboard_dir), static_url_path='')
    
    # Configure SocketIO with proper CORS and transport settings
    socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode='threading',  # Use threading for compatibility
        ping_timeout=60,  # Increase timeout to 60 seconds
        ping_interval=25,  # Send ping every 25 seconds
        logger=True,
        engineio_logger=True
    )
    
    # Register API blueprint
    app.register_blueprint(api)

    dispatcher = WSActionDispatcher(socketio)
    
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
        """Log socket connections without attempting to send a response.

        Returning data from a ``connect`` handler causes Werkzeug to raise
        ``AssertionError: write() before start_response`` when the WebSocket
        handshake upgrades from HTTP. The handshake expects either ``None`` or
        ``False`` (to reject the connection); any other value results in the
        WSGI stack trying to write a body before the upgrade completes. This
        keeps the handler side-effect free so the handshake can succeed.
        """

        logger.info("Client connected: sid=%s", request.sid)
    
    @socketio.on('disconnect')
    def handle_disconnect() -> None:
        sid = request.sid
        logger.info("Client disconnected: sid=%s", sid)
        dispatcher.forget_session(sid)

    @socketio.on('message')
    def handle_message(data: Any) -> None:
        sid = request.sid
        logger.info("Received message from %s: %s", sid, data)
        dispatcher.dispatch(sid, data)
    
    return app, socketio

def main() -> None:
    logging.basicConfig(level=logging.INFO)
    app, socketio = create_app()
    
    # Get host configuration - default to localhost for extension compatibility
    # For production, set VAMP_AGENT_HOST=0.0.0.0 to listen on all interfaces
    host = os.getenv("VAMP_AGENT_HOST", "127.0.0.1")
    port = int(os.getenv("VAMP_AGENT_PORT", "8080"))
    
    logger.info("Starting VAMP agent-as-app server on %s:%s", host, port)
    logger.info("Extension should connect to: ws://%s:%s", host, port)
    
    # Run the server with proper configuration
    socketio.run(
        app,
        host=host,
        port=port,
        debug=False,
        allow_unsafe_werkzeug=True,
        use_reloader=False  # Disable reloader in production
    )

if __name__ == "__main__":  # pragma: no cover
    main()
