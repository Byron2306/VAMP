"""Unified agent-as-app server exposing REST + websocket endpoints."""

from __future__ import annotations

import logging
import os
from typing import Any

from flask import Flask

from .agent_app.api import api
from .agent_app.app_state import agent_state

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(api)

    @app.get("/api/ping")
    def ping() -> Any:
        return {"status": "ok", "state": agent_state().health().last_updated}

    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    host = os.getenv("VAMP_AGENT_HOST", "0.0.0.0")
    port = int(os.getenv("VAMP_AGENT_PORT", "8080"))
    logger.info("Starting VAMP agent-as-app server on %s:%s", host, port)
    app.run(host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    main()
