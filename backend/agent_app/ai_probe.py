"""Telemetry helpers for tracking NWU Brain activity."""
from __future__ import annotations

import copy
import threading
import time
from typing import Any, Dict, List, Optional


def _preview(text: str, limit: int = 400) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _summarise_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summary: List[Dict[str, Any]] = []
    for tool in tools[:5]:
        if not isinstance(tool, dict):
            continue
        summary.append(
            {
                "tool": str(tool.get("tool") or tool.get("name") or tool.get("action") or ""),
                "status": str(tool.get("status") or tool.get("result") or ""),
                "items_found": tool.get("items_found"),
                "total_month_items": tool.get("total_month_items"),
            }
        )
    return summary


class AIRuntimeProbe:
    """Collects lightweight runtime diagnostics for AI interactions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    # ------------------------------------------------------------------
    def reset(self) -> None:
        with self._lock:
            self._start = time.time()
            self._connected: set[str] = set()
            self._last_socket_event: Optional[Dict[str, Any]] = None
            self._last_action: Optional[Dict[str, Any]] = None
            self._last_call: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    def note_socket(self, event: str, sid: str) -> None:
        with self._lock:
            if event == "connect":
                self._connected.add(sid)
            elif event == "disconnect":
                self._connected.discard(sid)
            self._last_socket_event = {
                "event": event,
                "sid": sid,
                "at": time.time(),
                "connected_clients": len(self._connected),
            }

    # ------------------------------------------------------------------
    def note_action(self, sid: str, action: str) -> None:
        with self._lock:
            self._last_action = {
                "sid": sid,
                "action": action,
                "at": time.time(),
            }

    # ------------------------------------------------------------------
    def record_call(
        self,
        *,
        question: str,
        mode: str,
        answer: str,
        tools: List[Dict[str, Any]],
        offline: bool,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            self._last_call = {
                "at": time.time(),
                "question": _preview(question),
                "mode": mode,
                "answer": _preview(answer),
                "tool_summary": _summarise_tools(tools),
                "offline": bool(offline),
                "error": error,
                "metadata": metadata or {},
            }

    # ------------------------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "uptime_s": max(0.0, time.time() - self._start),
                "connected_clients": len(self._connected),
                "last_socket_event": copy.deepcopy(self._last_socket_event),
                "last_action": copy.deepcopy(self._last_action),
                "last_call": copy.deepcopy(self._last_call),
            }


ai_runtime_probe = AIRuntimeProbe()


__all__ = ["ai_runtime_probe", "AIRuntimeProbe"]
