"""Socket.IO action dispatcher bridging the extension UI with the agent app."""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import os
import re
import threading
import traceback
import time
from functools import partial
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Tuple

from flask_socketio import SocketIO

from .. import STORE_DIR
from ..settings import VAMP_AGENT_ENABLED
try:  # pragma: no cover - optional dependency during tests
    from ..ollama_client import analyze_feedback_with_ollama, ask_ollama
except Exception:  # pragma: no cover - fallback when Ollama client unavailable
    analyze_feedback_with_ollama = None  # type: ignore[assignment]
    ask_ollama = None  # type: ignore[assignment]

try:  # pragma: no cover - Playwright may be optional in tests
    from ..vamp_agent import run_scan_active_ws
except Exception:  # pragma: no cover - degrade gracefully when agent missing
    run_scan_active_ws = None  # type: ignore[assignment]
from ..vamp_store import VampStore, _uid
from .ai_probe import ai_runtime_probe
from .app_state import agent_state
from ..vamp_agent_v2_1.performance_monitor import PerformanceMonitor
from ..vamp_agent_v2_1.self_aware_state import SelfAwareState

logger = logging.getLogger(__name__)

STORE_DIR.mkdir(parents=True, exist_ok=True)


def _record_ai_runtime(
    *,
    question: str,
    payload: Optional[Dict[str, Any]],
    mode: str,
    purpose: str,
    sid: str,
    context: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """Safely relay AI interaction metadata to the runtime probe.

    ``ai_runtime_probe`` is used by the health endpoints to surface recent
    interactions.  In the original application this helper used to live in a
    module that is no longer imported which resulted in a ``NameError`` at
    runtime (see issue reproduced in the user logs).  Re-creating the helper
    locally keeps the dispatcher decoupled while restoring observability.
    """

    try:
        payload = payload or {}
        tools = [dict(tool) for tool in payload.get("tools", []) if isinstance(tool, dict)]
        answer = str(
            payload.get("answer")
            or payload.get("brain_summary")
            or payload.get("summary")
            or ""
        )
        offline = bool(error)
        if not offline:
            offline = not ask_ollama or _looks_like_ai_error(answer)

        metadata = {
            "purpose": purpose,
            "sid": sid,
            "context": {
                key: context.get(key)
                for key in ("email", "name", "org", "year", "month")
                if context and context.get(key) is not None
            },
        }

        ai_runtime_probe.record_call(
            question=question,
            mode=mode,
            answer=answer,
            tools=tools,
            offline=offline,
            error=error,
            metadata=metadata,
        )
    except Exception:  # pragma: no cover - probe failures must not break flows
        logger.debug("Failed to record AI runtime information", exc_info=True)


_ACTION_BLOCK = re.compile(r"```(?:tool|action)\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def _basic_text_reply(question: str, role: str = "VAMP AI") -> str:
    """Return a deterministic, human-friendly fallback response."""

    prefix = f"[{role}]"
    text = (question or "").strip()
    if not text:
        return f"{prefix} I didn't receive a question. Please try again."

    lowered = text.lower()
    greetings = ("hello", "hi", "hey", "howzit", "morning", "afternoon")
    if any(word in lowered for word in greetings):
        return (
            f"{prefix} Hello! I'm still here to help summarise NWU evidence even without the "
            "full AI service. Let me know what you need."
        )

    if "who" in lowered and "you" in lowered:
        return (
            f"{prefix} I'm the VAMP assistant that keeps track of NWU compliance evidence. "
            "I can answer simple questions even when the LLM is offline."
        )

    return (
        f"{prefix} I can't reach the AI model right now, but you asked: \"{text}\". "
        "Please try again once the service reconnects."
    )


def _looks_like_ai_error(text: Any) -> bool:
    """Best-effort detection for the placeholder errors returned by ``ask_ollama``."""

    if not text:
        return False

    if not isinstance(text, str):
        text = str(text)

    lowered = text.strip().lower()
    return (
        lowered.startswith("(ai")
        or lowered.startswith("ai error")
        or "ai error" in lowered
        or "ai http" in lowered
        or "unexpected response format" in lowered
    )


def _strip_action_blocks(text: str) -> str:
    """Remove any ```tool``` or ```action``` blocks before returning a final answer."""

    if not text:
        return ""
    return _ACTION_BLOCK.sub("", text).strip()


def _extract_action(text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Return ``(action_dict, error)`` parsed from a ```tool``` block, if present."""

    if not text:
        return None, None

    match = _ACTION_BLOCK.search(text)
    if not match:
        return None, None

    raw_block = match.group(1).strip()
    try:
        payload = json.loads(raw_block)
        if not isinstance(payload, dict):
            return None, "Tool payload must be a JSON object"
        return payload, None
    except json.JSONDecodeError as exc:
        return None, f"Invalid tool JSON: {exc}"


def _uid_from(msg: Dict[str, Any]) -> str:
    email = (msg.get("email") or "").strip().lower()
    if email:
        return _uid(email)
    name = (msg.get("name") or "").strip().lower()
    org = (msg.get("org") or "nwu").strip().lower()
    return f"{name}@{org}" if name else "anon@nwu"


def _ok(action: str, data: Any | None = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"ok": True, "action": action}
    if data is not None:
        payload["data"] = data
    return payload


def _fail(action: str, error: Any) -> Dict[str, Any]:
    return {"ok": False, "action": action, "error": str(error)}


def _supports_structured_feedback(func: Optional[Any]) -> bool:
    code = getattr(func, "__code__", None)
    try:
        return bool(code and getattr(code, "co_argcount", 0) >= 2)
    except Exception:
        return False


HAS_STRUCTURED_FEEDBACK = _supports_structured_feedback(analyze_feedback_with_ollama)


_CONNECTOR_SPEC = {
    "scan_active": {
        "description": (
            "Scrape live evidence using the Playwright VAMP agent and add results to "
            "the evidence store."
        ),
        "arguments": {
            "url": "Required. Full URL for the platform to scrape (Outlook, OneDrive, Google Drive, eFundi).",
            "email": "Optional. Defaults to the enrolment e-mail.",
            "year": "Optional. Defaults to the provided payload year or current year.",
            "month": "Optional. Defaults to the provided payload month or current month.",
            "deep_read": "Optional boolean. When false, skips deep content extraction (defaults to true).",
        },
    }
}


class _SessionEmitter:
    """Helper that knows how to emit Socket.IO responses for a given session."""

    def __init__(self, socketio: SocketIO, sid: str) -> None:
        self._socketio = socketio
        self._sid = sid

    def ok(self, action: str, data: Any | None = None) -> None:
        self._socketio.emit("response", _ok(action, data), to=self._sid)

    def fail(self, action: str, error: Any) -> None:
        self._socketio.emit("response", _fail(action, error), to=self._sid)


class _AgentEventBridge:
    """Optional bridge that emits agent events to websocket clients."""

    def __init__(self, socketio: SocketIO, *, enabled: bool, interval_seconds: float = 15.0) -> None:
        self.enabled = enabled
        self._socketio = socketio
        self._health_interval = max(1.0, interval_seconds)
        self._state = SelfAwareState()
        self._performance = PerformanceMonitor()
        self._health_task_started = False
        if self.enabled:
            self._start_health_loop()

    def _start_health_loop(self) -> None:
        if self._health_task_started:
            return
        self._health_task_started = True

        def _loop() -> None:
            while self.enabled:
                try:
                    self.emit_health()
                except Exception:  # pragma: no cover - background observability must not break the app
                    logger.debug("agent_health emission failed", exc_info=True)
                time.sleep(self._health_interval)

        self._socketio.start_background_task(_loop)

    def emit_health(self) -> None:
        if not self.enabled:
            return
        payload = {
            "ts": time.time(),
            "state": self._state.snapshot(),
            "performance": self._performance.snapshot(),
        }
        self._socketio.emit("agent_health", payload)

    def record_evidence_routed(self, evidence: Iterable[Dict[str, Any]]) -> None:
        if not self.enabled:
            return

        items = [self._summarize_evidence(item) for item in evidence if isinstance(item, dict)]
        if not items:
            return

        self._state.increment("director_queue_depth", len(items))
        payload = {"ts": time.time(), "count": len(items), "items": items}
        self._socketio.emit("agent_evidence_routed", payload)

    def _summarize_evidence(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        evidence_id = evidence.get("evidence_id") or evidence.get("id") or evidence.get("uid")
        title = evidence.get("title") or evidence.get("subject") or evidence.get("name")
        return {
            "evidence_id": str(evidence_id or title or evidence.get("path") or "unknown"),
            "title": title,
            "platform": evidence.get("platform") or evidence.get("source"),
            "modality": evidence.get("modality"),
        }


class WSActionDispatcher:
    """Dispatch incoming Socket.IO ``message`` payloads to agent actions."""

    def __init__(self, socketio: SocketIO, store: Optional[VampStore] = None) -> None:
        self._socketio = socketio
        store_dir_env = os.getenv("VAMP_STORE_DIR")
        if store is None:
            base_dir = Path(store_dir_env).expanduser() if store_dir_env else STORE_DIR
            self._store = VampStore(str(base_dir))
        else:
            self._store = store
        self._lock = threading.Lock()
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._agent_enabled = (os.getenv("VAMP_AGENT_ENABLED", "0") or "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._agent_bridge = _AgentEventBridge(self._socketio, enabled=self._agent_enabled)

    # ------------------------------------------------------------------
    def forget_session(self, sid: str) -> None:
        """Remove cached context for a disconnected websocket session."""

        self._sessions.pop(sid, None)

    def _session(self, sid: str) -> Dict[str, Any]:
        return self._sessions.setdefault(sid, {})

    def _remember_context(self, sid: str, msg: Dict[str, Any]) -> Dict[str, Any]:
        ctx = self._session(sid)
        if not isinstance(msg, dict):
            return ctx

        email = (msg.get("email") or "").strip()
        if email:
            ctx["email"] = email

        name = (msg.get("name") or "").strip()
        if name:
            ctx["name"] = name

        org = (msg.get("org") or "").strip()
        if org:
            ctx["org"] = org

        if "year" in msg:
            try:
                ctx["year"] = int(msg["year"])
            except (TypeError, ValueError):
                pass

        if "month" in msg:
            try:
                ctx["month"] = int(msg["month"])
            except (TypeError, ValueError):
                pass

        return ctx

    def _resolve_user(self, sid: str, msg: Dict[str, Any]) -> Tuple[str, str]:
        ctx = self._session(sid)
        email = (msg.get("email") or ctx.get("email") or "").strip()
        if email:
            return email, _uid(email)

        name = (msg.get("name") or ctx.get("name") or "").strip().lower()
        org = (msg.get("org") or ctx.get("org") or "nwu").strip().lower() or "nwu"
        if name:
            return "", f"{name}@{org}"
        return "", "anon@nwu"

    def _resolve_year(self, sid: str, msg: Dict[str, Any]) -> int:
        ctx = self._session(sid)
        if "year" in msg:
            try:
                ctx["year"] = int(msg["year"])
            except (TypeError, ValueError):
                pass
        stored = ctx.get("year")
        if isinstance(stored, int):
            return stored
        return _dt.datetime.utcnow().year

    def _resolve_month(self, sid: str, msg: Dict[str, Any]) -> int:
        ctx = self._session(sid)
        if "month" in msg:
            try:
                ctx["month"] = int(msg["month"])
            except (TypeError, ValueError):
                pass
        stored = ctx.get("month")
        if isinstance(stored, int):
            return stored
        return _dt.datetime.utcnow().month

    # ------------------------------------------------------------------
    def dispatch(self, sid: str, payload: Any) -> None:
        """Route an incoming payload to the appropriate handler."""

        if not isinstance(payload, dict):
            logger.warning("Rejecting non-dict websocket payload: %r", payload)
            self._socketio.emit("response", _fail("ERROR", "invalid_payload"), to=sid)
            return

        action_raw = payload.get("action")
        action = str(action_raw or "").upper()
        if not action:
            self._socketio.emit("response", _fail("ERROR", "missing_action"), to=sid)
            return

        self._remember_context(sid, payload)

        handler_name = f"_handle_{action.lower()}"
        handler = getattr(self, handler_name, None)
        if handler is None:
            logger.warning("Unsupported websocket action %r", action_raw)
            self._socketio.emit("response", _fail(action, "unsupported_action"), to=sid)
            return

        ai_runtime_probe.note_action(sid, action)
        try:
            handler(sid, payload)
        except Exception as exc:  # pragma: no cover - defensive programming
            logger.exception("Handler %s raised", handler_name)
            self._socketio.emit("response", _fail(action, str(exc)), to=sid)

    # ------------------------------------------------------------------
    def _handle_enrol(self, sid: str, msg: Dict[str, Any]) -> None:
        session = _SessionEmitter(self._socketio, sid)
        email = (msg.get("email") or "").strip()
        if not email:
            session.fail("ENROL", "Email required")
            return
        name = (msg.get("name") or "").strip()
        org = (msg.get("org") or "NWU").strip() or "NWU"
        with self._lock:
            profile = self._store.enroll(email, name, org)
        ctx = self._session(sid)
        ctx.update({"email": email, "name": name, "org": org})
        session.ok("ENROL", profile)

    def _handle_get_state(self, sid: str, msg: Dict[str, Any]) -> None:
        session = _SessionEmitter(self._socketio, sid)
        email, uid = self._resolve_user(sid, msg)
        year = self._resolve_year(sid, msg)
        target_id = email or uid
        with self._lock:
            year_doc = self._store.get_year_doc_with_items(target_id, year)
        session.ok("GET_STATE", {"year_doc": year_doc})

    def _handle_finalise_month(self, sid: str, msg: Dict[str, Any]) -> None:
        session = _SessionEmitter(self._socketio, sid)
        email, uid = self._resolve_user(sid, msg)
        target = email or uid
        year = self._resolve_year(sid, msg)
        month = self._resolve_month(sid, msg)
        with self._lock:
            doc = self._store.finalise_month(target, year, month)
        session.ok("FINALISE_MONTH", doc)

    def _handle_export_month(self, sid: str, msg: Dict[str, Any]) -> None:
        session = _SessionEmitter(self._socketio, sid)
        email, uid = self._resolve_user(sid, msg)
        target = email or uid
        year = self._resolve_year(sid, msg)
        month = self._resolve_month(sid, msg)
        with self._lock:
            path = self._store.export_month_csv(target, year, month)
        session.ok("EXPORT_MONTH", {"path": str(path)})

    def _handle_compile_year(self, sid: str, msg: Dict[str, Any]) -> None:
        session = _SessionEmitter(self._socketio, sid)
        email, uid = self._resolve_user(sid, msg)
        target = email or uid
        year = self._resolve_year(sid, msg)
        with self._lock:
            path = self._store.export_year_csv(target, year)
        session.ok("COMPILE_YEAR", {"path": str(path)})

    def _handle_scan_active(self, sid: str, msg: Dict[str, Any]) -> None:
        if not VAMP_AGENT_ENABLED:
            self._socketio.emit(
                "response",
                _fail("SCAN_ACTIVE", "VAMP agent disabled (set VAMP_AGENT_ENABLED=1 to enable)"),
                to=sid,
            )
            return

        if run_scan_active_ws is None:
            self._socketio.emit("response", _fail("SCAN_ACTIVE", "vamp_agent not available"), to=sid)
            return

        self._socketio.emit("response", _ok("SCAN_ACTIVE/STARTED"), to=sid)
        self._start_async(self._run_scan_active, sid, msg)

    def _handle_ask(self, sid: str, msg: Dict[str, Any]) -> None:
        self._start_async(self._run_ask, sid, msg)

    def _handle_ask_feedback(self, sid: str, msg: Dict[str, Any]) -> None:
        self._start_async(self._run_ask_feedback, sid, msg)

    # ------------------------------------------------------------------
    def _start_async(self, func: Callable[..., Awaitable[None]], *args: Any) -> None:
        def runner() -> None:
            asyncio.run(func(*args))

        self._socketio.start_background_task(runner)

    # ------------------------------------------------------------------
    async def _run_scan_active(self, sid: str, msg: Dict[str, Any]) -> None:
        session = _SessionEmitter(self._socketio, sid)
        if not VAMP_AGENT_ENABLED:
            session.fail("SCAN_ACTIVE", "VAMP agent disabled (enable VAMP_AGENT_ENABLED to run scans)")
            return
        email_raw, uid = self._resolve_user(sid, msg)
        email = (email_raw or "").strip().lower() or uid
        year = self._resolve_year(sid, msg)
        month = self._resolve_month(sid, msg)
        url = (msg.get("url") or "https://outlook.office365.com/mail/").strip()
        deep_read = bool(msg.get("deep_read", True))

        logger.info("Starting scan for %s %d-%02d", uid, year, month)
        context_snapshot = dict(msg)
        context_snapshot.setdefault("email", email)
        context_snapshot.setdefault("year", year)
        context_snapshot.setdefault("month", month)

        async def on_progress(progress: float, status: str) -> None:
            payload = {
                "pct": float(progress),
                "progress": max(0.0, min(1.0, float(progress) / 100.0)),
                "status": status or "",
            }
            session.ok("SCAN_ACTIVE/PROGRESS", payload)

        orchestrated: Optional[Dict[str, Any]] = None
        orchestrator_error: Optional[str] = None
        autop_prompt = (
            "Execute the scan_active connector for the provided user context right now. "
            f"Target URL: {url}. Deep read: {'true' if deep_read else 'false'}. "
            "After the connector finishes, summarise the scan outcome, including how many "
            "new evidence items were stored."
        )
        brain_msg: Optional[Dict[str, Any]] = None
        try:
            if ask_ollama:
                brain_msg = dict(context_snapshot)
                brain_msg.setdefault("email", email or uid)
                brain_msg.setdefault("year", year)
                brain_msg.setdefault("month", month)
                brain_msg.setdefault("url", url)
                brain_msg.setdefault("deep_read", deep_read)
                orchestrated = await _orchestrate_answer(
                    brain_msg,
                    autop_prompt,
                    store=self._store,
                    progress_cb=on_progress,
                    purpose="scan",
                    agent_bridge=self._agent_bridge,
                )
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("AI orchestrated scan failed: %s", exc)
            orchestrator_error = str(exc)
            orchestrated = None

        if brain_msg is not None:
            _record_ai_runtime(
                question=autop_prompt,
                payload=orchestrated,
                mode="scan",
                purpose="scan_active",
                sid=sid,
                context=brain_msg,
                error=orchestrator_error,
            )

        try:
            added = 0
            total = 0
            summary_text = ""
            tool_payload: List[Dict[str, Any]] = []

            if orchestrated and orchestrated.get("tools"):
                raw_tools = orchestrated.get("tools", [])
                tool_payload = [dict(t) for t in raw_tools if isinstance(t, dict)]
                for obs in tool_payload:
                    if (obs.get("tool") or "").lower() == "scan_active" and obs.get("status") == "success":
                        try:
                            added = int(obs.get("items_found", 0) or 0)
                        except Exception:
                            added = 0
                        try:
                            total = int(obs.get("total_month_items", 0) or 0)
                        except Exception:
                            total = 0
                summary_text = str(orchestrated.get("answer") or "").strip()

                if added or total:
                    await on_progress(95.0, "Summarising NWU Brain results...")
                    await on_progress(100.0, "Scan complete")
                    session.ok(
                        "SCAN_ACTIVE/COMPLETE",
                        {
                            "added": added,
                            "total_evidence": total,
                            **({"brain_summary": summary_text} if summary_text else {}),
                            **({"tools": tool_payload} if tool_payload else {}),
                        },
                    )
                    agent_state().health()  # Refresh health timestamp
                    return

            results = await run_scan_active_ws(
                email=email or uid,
                year=year,
                month=month,
                url=url,
                deep_read=deep_read,
                progress_callback=on_progress,
            )

            results = results or []
            self._agent_bridge.record_evidence_routed(results)
            if not results:
                await on_progress(100.0, "Scan complete — no new items")
                session.ok(
                    "SCAN_ACTIVE/COMPLETE",
                    {
                        "added": 0,
                        "total_evidence": 0,
                        "brain_summary": "The scan completed without finding new evidence artefacts.",
                    },
                )
                agent_state().health()
                return

            with self._lock:
                month_doc = self._store.add_items(uid, year, month, results)
            added = len(results)
            total = len(month_doc.get("items", []))
            summary_text = (
                f"Manual fallback added {added} new evidence items. "
                f"The month now tracks {total} total artefacts."
            )

            for item in results:
                if isinstance(item, dict):
                    submit_evidence_from_vamp({**item, "source": item.get("source") or "scan_active"})

            session.ok(
                "SCAN_ACTIVE/COMPLETE",
                {
                    "added": added,
                    "total_evidence": total,
                    "brain_summary": summary_text,
                    "tools": [
                        {
                            "tool": "scan_active",
                            "status": "success",
                            "items_found": added,
                            "total_month_items": total,
                            "mode": "fallback",
                        }
                    ],
                },
            )
        except Exception as exc:
            logger.error("Scan failed: %s", traceback.format_exc())
            session.fail("SCAN_ACTIVE", str(exc))
        finally:
            agent_state().health()

    async def _run_ask(self, sid: str, msg: Dict[str, Any]) -> None:
        session = _SessionEmitter(self._socketio, sid)
        context_msg = dict(msg)
        email, uid = self._resolve_user(sid, context_msg)
        if email:
            context_msg.setdefault("email", email)
        else:
            context_msg.setdefault("email", uid)

        ctx = self._session(sid)
        if ctx.get("name") and not context_msg.get("name"):
            context_msg["name"] = ctx.get("name")
        if ctx.get("org") and not context_msg.get("org"):
            context_msg["org"] = ctx.get("org")

        year = self._resolve_year(sid, context_msg)
        month = self._resolve_month(sid, context_msg)
        context_msg["year"] = year
        context_msg["month"] = month

        messages = context_msg.get("messages", [])
        question = "\n\n".join(
            str(m.get("content", "")) for m in messages if isinstance(m, dict)
        ).strip()

        mode = str(context_msg.get("mode") or "").strip().lower() or "ask"
        is_brain_scan = mode in {"brain_scan", "scan", "scan_via_brain"}
        purpose = "scan" if is_brain_scan else "ask"

        async def forward_progress(progress: float, status: str) -> None:
            payload = {
                "pct": float(progress),
                "progress": max(0.0, min(1.0, float(progress) / 100.0)),
                "status": status or "",
            }
            session.ok("SCAN_ACTIVE/PROGRESS", payload)

        if not question:
            session.ok(
                "ASK",
                {"answer": _basic_text_reply("", role="VAMP AI"), "mode": mode, "tools": []},
            )
            return

        if is_brain_scan:
            if not VAMP_AGENT_ENABLED:
                session.fail("SCAN_ACTIVE", "VAMP agent disabled (enable VAMP_AGENT_ENABLED to run scans)")
                session.ok(
                    "ASK",
                    {
                        "answer": _basic_text_reply(question, role="VAMP AI"),
                        "mode": mode,
                        "tools": [],
                    },
                )
                return
            session.ok("SCAN_ACTIVE/STARTED")

        try:
            orchestration = await _orchestrate_answer(
                context_msg,
                question,
                store=self._store,
                progress_cb=forward_progress if is_brain_scan else None,
                purpose="scan" if is_brain_scan else "ask",
                agent_bridge=self._agent_bridge,
            )
        except Exception as exc:
            logger.warning("orchestration failed: %s", exc)
            if is_brain_scan:
                session.fail("SCAN_ACTIVE", str(exc))
            session.ok(
                "ASK",
                {
                    "answer": _basic_text_reply(question, role="VAMP AI"),
                    "mode": mode,
                    "tools": [],
                },
            )
            return

        payload = dict(orchestration or {})
        payload.setdefault("tools", [])
        payload["mode"] = mode

        if is_brain_scan:
            tools = [dict(t) for t in payload.get("tools", []) if isinstance(t, dict)]
            added = 0
            total = 0
            for obs in tools:
                tool_name = str(obs.get("tool") or "").lower()
                if tool_name == "scan_active" and obs.get("status") == "success":
                    try:
                        added = int(obs.get("items_found", 0) or 0)
                    except Exception:
                        added = 0
                    try:
                        total = int(obs.get("total_month_items", 0) or 0)
                    except Exception:
                        total = 0

            summary_text = str(payload.get("answer") or "").strip()
            complete_payload: Dict[str, Any] = {
                "added": added,
                "total_evidence": total,
            }
            if summary_text:
                complete_payload["brain_summary"] = summary_text
            if tools:
                complete_payload["tools"] = tools
            session.ok("SCAN_ACTIVE/COMPLETE", complete_payload)

        session.ok("ASK", payload)
        _record_ai_runtime(
            question=question,
            payload=payload,
            mode=mode,
            purpose=purpose,
            sid=sid,
            context=context_msg,
        )

    async def _run_ask_feedback(self, sid: str, msg: Dict[str, Any]) -> None:
        session = _SessionEmitter(self._socketio, sid)
        messages = msg.get("messages", [])
        question = "\n\n".join(
            str(m.get("content", "")) for m in messages if isinstance(m, dict)
        ).strip()

        answer = _basic_text_reply("", role="VAMP Assessor")

        if question:
            loop = asyncio.get_running_loop()
            if analyze_feedback_with_ollama and HAS_STRUCTURED_FEEDBACK:

                def _call_feedback() -> str:
                    result = analyze_feedback_with_ollama([], [question])  # type: ignore[arg-type]
                    if isinstance(result, dict):
                        answers = result.get("answers") or []
                        if answers:
                            first = answers[0]
                            summary = str(first.get("summary", "")).strip()
                            verdict = str(first.get("verdict", "")).strip()
                            verdict_part = f" Verdict: {verdict}." if verdict else ""
                            return (summary or "(No summary provided)") + verdict_part
                    return "(AI returned no structured feedback)"

                try:
                    answer = await loop.run_in_executor(None, _call_feedback)
                except Exception as exc:  # pragma: no cover - resilience path
                    logger.warning("analyze_feedback_with_ollama failed: %s", exc)
                    answer = _basic_text_reply(question, role="VAMP Assessor")
            elif ask_ollama:
                try:
                    answer = await loop.run_in_executor(None, partial(ask_ollama, question))
                    if _looks_like_ai_error(answer):
                        answer = _basic_text_reply(question, role="VAMP Assessor")
                except Exception as exc:  # pragma: no cover
                    logger.warning("ask_ollama feedback fallback failed: %s", exc)
                    answer = _basic_text_reply(question, role="VAMP Assessor")
            else:
                answer = _basic_text_reply(question, role="VAMP Assessor")

        payload = {"answer": answer, "mode": "assessor", "tools": []}
        session.ok("ASK_FEEDBACK", payload)
        if question:
            _record_ai_runtime(
                question=question,
                payload=payload,
                mode="assessor",
                purpose="assessor",
                sid=sid,
                context=msg,
            )


async def _execute_action(
    dispatcher_store: VampStore,
    action: Dict[str, Any],
    base_msg: Dict[str, Any],
    uid: str,
    *,
    progress_cb: Optional[Callable[[float, str], Awaitable[None]]] = None,
    agent_bridge: Optional[_AgentEventBridge] = None,
) -> Dict[str, Any]:
    """Execute an orchestrator action and return an observation dict."""

    name = str(action.get("tool") or action.get("action") or action.get("name") or "").strip()
    args = action.get("arguments") or action.get("args") or action.get("parameters") or {}
    if not isinstance(args, dict):
        args = {}

    observation: Dict[str, Any] = {
        "tool": name or "",
        "status": "error",
        "arguments": args,
    }

    if not name:
        observation["error"] = "Tool name missing"
        return observation

    if not VAMP_AGENT_ENABLED:
        observation["error"] = "VAMP agent disabled (enable VAMP_AGENT_ENABLED to run tools)"
        return observation

    if name != "scan_active":
        observation["error"] = f"Unknown tool: {name}"
        return observation

    if run_scan_active_ws is None:
        observation["error"] = "VAMP agent not available"
        return observation

    email = (args.get("email") or base_msg.get("email") or uid or "").strip()
    year = int(args.get("year") or base_msg.get("year") or _dt.datetime.utcnow().year)
    month = int(args.get("month") or base_msg.get("month") or _dt.datetime.utcnow().month)
    url = (args.get("url") or base_msg.get("url") or "").strip()
    deep_read = args.get("deep_read")
    if isinstance(deep_read, str):
        deep_read = deep_read.lower() not in {"0", "false", "no"}
    elif deep_read is None:
        deep_read = bool(base_msg.get("deep_read", True))
    else:
        deep_read = bool(deep_read)

    if not url:
        observation["error"] = "URL is required for scan_active"
        return observation

    progress_log: List[Dict[str, Any]] = []

    async def capture_progress(progress: float, status: str) -> None:
        progress_entry = {"progress": progress, "status": status}
        progress_log.append(progress_entry)
        if progress_cb:
            try:
                await progress_cb(progress, status)
            except Exception:  # pragma: no cover - progress reporting best effort
                logger.debug("Progress callback failed", exc_info=True)

    try:
        results = await run_scan_active_ws(
            email=email,
            year=year,
            month=month,
            url=url,
            deep_read=bool(deep_read),
            progress_callback=capture_progress,
        )
    except Exception as exc:  # pragma: no cover
        observation["error"] = f"Scan failed: {exc}"
        observation["progress"] = progress_log
        return observation

    results = results or []
    if agent_bridge:
        agent_bridge.record_evidence_routed(results)

    try:
        month_doc = dispatcher_store.add_items(email or uid, year, month, results)
    except Exception as exc:
        observation["error"] = f"Store update failed: {exc}"
        observation["progress"] = progress_log
        observation["items_found"] = len(results)
        return observation

    sample: List[Dict[str, Any]] = []
    for item in results[: min(5, len(results))]:
        sample.append(
            {
                "title": item.get("title") or item.get("subject") or item.get("name"),
                "platform": item.get("platform") or item.get("source"),
                "score": item.get("score"),
                "band": item.get("band"),
                "date": item.get("date") or item.get("modified"),
            }
        )

    observation.update(
        {
            "status": "success",
            "items_found": len(results),
            "total_month_items": len(month_doc.get("items", [])),
            "progress": progress_log[-5:],
            "sample": sample,
        }
    )
    logger.info(
        "Autop connector scan_active completed for %s (items=%d, total=%d)",
        email or uid,
        len(results),
        len(month_doc.get("items", [])),
    )
    return observation


async def _orchestrate_answer(
    msg: Dict[str, Any],
    question: str,
    *,
    store: VampStore,
    progress_cb: Optional[Callable[[float, str], Awaitable[None]]] = None,
    purpose: str = "ask",
    agent_bridge: Optional[_AgentEventBridge] = None,
) -> Dict[str, Any]:
    """Drive an LLM loop that can invoke connectors before producing an answer."""

    if not ask_ollama:
        return {"answer": _basic_text_reply(question, role="VAMP AI"), "tools": []}

    uid = _uid_from(msg)
    email = (msg.get("email") or "").strip() or uid
    year = int(msg.get("year") or _dt.datetime.utcnow().year)
    month = int(msg.get("month") or _dt.datetime.utcnow().month)
    loop = asyncio.get_running_loop()
    history: List[Tuple[str, str]] = []
    tool_summaries: List[Dict[str, Any]] = []
    max_steps = 3 if purpose == "scan" else 5

    existing_items: List[Dict[str, Any]] = []
    evidence_stats: Dict[str, Any] = {}

    try:
        existing_items = store.get_evidence_for_display(email, year, month)
    except Exception:
        existing_items = []

    try:
        evidence_stats = store.get_evidence_stats(email, year)
    except Exception:
        evidence_stats = {}

    evidence_overview = f"Evidence store for {year}-{month:02d}: {len(existing_items)} items"
    scored_items = evidence_stats.get("scored_items") if evidence_stats else None
    average_score = evidence_stats.get("average_score") if evidence_stats else None
    if isinstance(scored_items, int) and scored_items:
        try:
            avg = float(average_score) if average_score is not None else None
        except (TypeError, ValueError):
            avg = None
        if avg is not None:
            evidence_overview += f" (avg score {avg:.2f} across {scored_items} scored items)"
    locked_months = evidence_stats.get("locked_months") if evidence_stats else []
    if isinstance(locked_months, list) and month in locked_months:
        evidence_overview += ", month locked"

    sample_lines: List[str] = []
    for item in existing_items[:3]:
        title = item.get("title") or item.get("subject") or item.get("name") or "(untitled)"
        platform = item.get("platform") or item.get("source") or ""
        score = item.get("score")
        try:
            score_display = f"{float(score):.1f}" if isinstance(score, (int, float)) else "n/a"
        except Exception:
            score_display = "n/a"
        band = item.get("band") or ""
        band_display = f" ({band})" if band else ""
        sample_lines.append(
            f"- {title} [{platform}] → score {score_display}{band_display}"
        )

    evidence_samples = "\n".join(sample_lines) if sample_lines else "(no stored evidence summaries)"
    connector_doc = json.dumps(_CONNECTOR_SPEC, ensure_ascii=False, indent=2)
    context_line = f"User context → email: {email}, year: {year}, month: {month}"

    base_instructions = (
        "You are the NWU Brain Autop orchestrator for VAMP. Reason in deliberate steps before replying. "
        "Always inspect the stored NWU evidence summaries before deciding whether you need a live connector. "
    )

    if purpose == "scan":
        instructions = (
            base_instructions
            + "Your task is to run the scan_active connector exactly once using the provided context. "
            "Call scan_active immediately, wait for the observation, then summarise the extraction outcome for the UI. "
            "Do not produce a final answer until after you have reviewed the tool response."
        )
    else:
        instructions = (
            base_instructions
            + "If you need fresh evidence, call a connector by responding with ONLY a JSON object inside a ```tool``` block. "
            "Example: ```tool\n{\"tool\":\"scan_active\",\"arguments\":{\"url\":\"https://outlook.office.com/mail/\",\"email\":\"user@nwu.ac.za\"}}\n```. "
            "After a connector runs, review the tool result from the history and continue reasoning. "
            "When you are ready to respond, provide a concise written answer with citations of the evidence summaries."
        )

    for _ in range(max_steps):
        history_lines = []
        for role, content in history:
            prefix = "TOOL" if role == "tool" else "ASSISTANT"
            history_lines.append(f"{prefix}: {content}")

        prompt_parts = [
            instructions,
            f"Available connectors: {connector_doc}",
            context_line,
            evidence_overview,
            "Stored evidence samples:",
            evidence_samples,
            "History:" if history_lines else "History: (none)",
            "\n".join(history_lines) if history_lines else "",
            "Question:",
            question,
        ]

        prompt = "\n\n".join(part for part in prompt_parts if part)

        try:
            response = await loop.run_in_executor(None, partial(ask_ollama, prompt))
        except Exception as exc:
            return {
                "answer": f"[VAMP AI] (error) {exc}",
                "tools": tool_summaries,
            }

        response_raw = response or ""
        response_text = response_raw.strip()
        if _looks_like_ai_error(response_text):
            fallback = _basic_text_reply(question, role="VAMP AI")
            if tool_summaries:
                formatted = "\n".join(
                    f"- {obs.get('tool') or 'unknown'} → {obs.get('status')} (items={obs.get('items_found', 0)})"
                    for obs in tool_summaries
                )
                fallback = f"{fallback}\n\nTools used:\n{formatted}".strip()
            return {"answer": fallback, "tools": tool_summaries}

        history.append(("assistant", _strip_action_blocks(response_raw)))

        action, error = _extract_action(response_raw)
        if error:
            error_obs = {"tool": "", "status": "error", "error": error}
            history.append(("tool", json.dumps(error_obs, ensure_ascii=False)))
            tool_summaries.append(error_obs)
            continue

        if action:
            observation = await _execute_action(
                store,
                action,
                msg,
                uid,
                progress_cb=progress_cb,
                agent_bridge=agent_bridge,
            )
            tool_summaries.append(observation)
            history.append(("tool", json.dumps(observation, ensure_ascii=False)))
            continue

        final_answer = _strip_action_blocks(response_raw)
        if tool_summaries:
            formatted = "\n".join(
                f"- {obs.get('tool') or 'unknown'} → {obs.get('status')} (items={obs.get('items_found', 0)})"
                for obs in tool_summaries
            )
            final_answer = f"{final_answer}\n\nTools used:\n{formatted}".strip()
        return {"answer": final_answer or "(AI returned no answer)", "tools": tool_summaries}

    fallback = _basic_text_reply(question, role="VAMP AI")
    if history:
        fallback = f"{fallback}\n\nLast AI output: {history[-1][1]}".strip()
    if tool_summaries:
        formatted = "\n".join(
            f"- {obs.get('tool') or 'unknown'} → {obs.get('status')} (items={obs.get('items_found', 0)})"
            for obs in tool_summaries
        )
        fallback = f"{fallback}\n\nTools used:\n{formatted}".strip()
    return {"answer": fallback, "tools": tool_summaries}


__all__ = ["WSActionDispatcher"]

