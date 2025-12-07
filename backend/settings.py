"""Shared configuration helpers for the VAMP backend."""

from __future__ import annotations

import os
from typing import Any


def env_flag(name: str, default: bool = False) -> bool:
    """Parse a boolean-like environment variable.

    Accepts common truthy strings (``1``, ``true``, ``yes``, ``on``). Any other
    value falls back to ``False`` so the safer path is taken by default.
    """

    raw: Any = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


# Disable the agent and bridge features by default until explicitly enabled.
VAMP_AGENT_ENABLED: bool = env_flag("VAMP_AGENT_ENABLED", False)

# Centralised network configuration so scripts and code share defaults.
def _clean_host(value: str | None, default: str) -> str:
    """Return a sanitized host string without leading/trailing whitespace.

    ``socket.getaddrinfo`` raises ``gaierror`` when given hosts such as
    ``"127.0.0.1 "`` (note trailing space). The setup scripts on Windows
    occasionally introduce stray whitespace via environment variables, so we
    normalise here to ensure consistent behaviour across platforms.
    """

    if value is None:
        return default

    cleaned = value.strip()
    return cleaned or default


VAMP_AGENT_HOST: str = _clean_host(os.getenv("VAMP_AGENT_HOST"), "127.0.0.1")
VAMP_AGENT_PORT: int = int(os.getenv("VAMP_AGENT_PORT", "8080"))

# Legacy plain WebSocket bridge (optional).
APP_HOST: str = _clean_host(os.getenv("APP_HOST"), VAMP_AGENT_HOST)
APP_PORT: int = int(os.getenv("APP_PORT", "8765"))

__all__ = [
    "env_flag",
    "VAMP_AGENT_ENABLED",
    "VAMP_AGENT_HOST",
    "VAMP_AGENT_PORT",
    "APP_HOST",
    "APP_PORT",
]
