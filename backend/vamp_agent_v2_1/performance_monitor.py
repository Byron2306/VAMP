"""Performance monitoring abstractions for Autonomous Agent v2.1.

Provides a lightweight wrapper around ``psutil`` so the agent can observe CPU
and memory usage without introducing heavy dependencies or behaviour changes.
"""
from __future__ import annotations

import importlib
from typing import Dict

psutil_spec = importlib.util.find_spec("psutil")
psutil = importlib.import_module("psutil") if psutil_spec else None


class PerformanceMonitor:
    """Expose minimal performance metrics with graceful degradation."""

    def __init__(self) -> None:
        self.available = psutil is not None

    def snapshot(self) -> Dict[str, float]:
        """Return CPU and memory statistics if available.

        When ``psutil`` is unavailable, returns an empty dictionary to avoid
        breaking callers in constrained environments.
        """

        if not self.available:
            return {}

        return {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
        }
