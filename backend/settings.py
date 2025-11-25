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

__all__ = ["env_flag", "VAMP_AGENT_ENABLED"]
