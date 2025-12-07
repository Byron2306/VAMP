"""Agent-as-app infrastructure for VAMP."""

from __future__ import annotations

from pathlib import Path

from .. import DATA_DIR, STATE_DIR

AGENT_STATE_DIR = STATE_DIR / "agent_app"
AGENT_CONFIG_DIR = DATA_DIR / "agent_app"
AGENT_LOG_DIR = AGENT_STATE_DIR / "logs"

for path in (AGENT_STATE_DIR, AGENT_CONFIG_DIR, AGENT_LOG_DIR):
    path.mkdir(parents=True, exist_ok=True)

__all__ = [
    "AGENT_STATE_DIR",
    "AGENT_CONFIG_DIR",
    "AGENT_LOG_DIR",
]
# Import local_scan_handler to patch WSActionDispatcher with SCAN_LOCAL support
from . import local_scan_handler
