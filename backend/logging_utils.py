"""Shared logging helpers to keep console output concise.

The interactive PowerShell experience should only surface single-line errors
while still preserving full diagnostics for post-mortem analysis. This module
configures loggers with a quiet console handler and a rotating file handler
for deep debugging. It also records structured integrity feedback to an Excel
ledger so background health checks stay invisible to end users.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict

import pandas as pd

LOG_DIR = Path(os.environ.get("VAMP_LOG_DIR", Path(__file__).parent / "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_FEEDBACK_PATH = LOG_DIR / "feedback_tags.xlsx"


def configure_quiet_logger(
    name: str,
    *,
    env_level_var: str = "VAMP_LOG_LEVEL",
    default_console_level: str = "ERROR",
    file_name: str = "vamp.log",
    file_level: str | None = None,
) -> logging.Logger:
    """Create a logger that only shows concise errors on the console.

    Console logs default to ``ERROR`` with a short format. A rotating file
    handler captures richer context for troubleshooting without spamming live
    terminals. The configuration is idempotent per logger name.
    """

    logger = logging.getLogger(name)
    if getattr(logger, "_vamp_configured", False):
        return logger

    logger.setLevel(logging.DEBUG)

    console_level_name = os.environ.get(env_level_var, default_console_level).upper()
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, console_level_name, logging.ERROR))
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    file_level_name = (file_level or os.environ.get(f"{env_level_var}_FILE", "INFO")).upper()
    file_handler = RotatingFileHandler(LOG_DIR / file_name, maxBytes=1_000_000, backupCount=3)
    file_handler.setLevel(getattr(logging, file_level_name, logging.INFO))
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
    )

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.propagate = False
    logger._vamp_configured = True  # type: ignore[attr-defined]
    return logger


def record_feedback_tag(
    event: str,
    message: str,
    *,
    severity: str = "info",
    context: Dict[str, Any] | None = None,
    path: Path = DEFAULT_FEEDBACK_PATH,
) -> None:
    """Persist a structured feedback event to an Excel ledger.

    The ledger keeps internal integrity signals out of the live UI while
    preserving breadcrumbs for support teams. Failures to write feedback
    entries are intentionally silent to avoid impacting runtime behavior.
    """

    try:
        payload: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
            "severity": severity,
            "event": event,
            "message": message,
            "context": json.dumps(context or {}),
        }

        new_frame = pd.DataFrame([payload])
        if path.exists():
            try:
                existing = pd.read_excel(path)
                combined = pd.concat([existing, new_frame], ignore_index=True)
            except Exception:
                combined = new_frame
        else:
            combined = new_frame

        with pd.ExcelWriter(path, engine="openpyxl", mode="w") as writer:
            combined.to_excel(writer, index=False)
    except Exception:
        # Feedback persistence must never interrupt runtime behavior.
        return
