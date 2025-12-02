#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VAMP WebSocket Bridge — FINAL WORKING VERSION
Includes: SCAN_ACTIVE + ASK + ENROL + GET_STATE + FINALISE + EXPORT
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import os
import re
import traceback
from functools import partial
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import websockets
try:  # websockets >= 10
    from websockets.server import WebSocketServerProtocol
except ImportError:  # Compatibility for older deployments
    from websockets.legacy.server import WebSocketServerProtocol  # type: ignore

from . import STORE_DIR
from .logging_utils import configure_quiet_logger, record_feedback_tag
from .vamp_store import VampStore, _uid

# --- Import agent ---
try:
    from .vamp_agent import run_scan_active_ws
except Exception as e:
    logging.error(f"Failed to import vamp_agent: {e}")
    run_scan_active_ws = None

# --- Configuration ---
APP_HOST = os.environ.get("APP_HOST", "127.0.0.1")
APP_PORT = int(os.environ.get("APP_PORT", "8765"))
STORE_DIR.mkdir(parents=True, exist_ok=True)
store = VampStore(str(STORE_DIR))

# Default to quiet output unless explicitly overridden.
logger = configure_quiet_logger(
    "vamp.ws",
    env_level_var="VAMP_WS_LOG_LEVEL",
    default_console_level="ERROR",
    file_name="ws_bridge.log",
)

try:# Ollama client removed - no AI API dependencies
    # These are stubs for compatibility
    ask_ollama = None  # type: ignore    logger.warning(f"Ollama client not available: {e}")
    ask_ollama = None  # type: ignore
    code = getattr(func, "__code__", None)
    try:
        return bool(code and getattr(code, "co_argcount", 0) >= 2)
    except Exception:
        return False


HAS_STRUCTURED_FEEDBACK = _supports_structured_feedback(analyze_feedback_with_ollama)

# --- LLM Orchestration helpers ---
_ACTION_BLOCK = re.compile(r"```(?:tool|action)\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)

_CONNECTOR_SPEC = {
    "scan_active": {
        "description": "Scrape live evidence using the Playwright VAMP agent and add results to the evidence store.",
        "arguments": {
            "url": "Required. Full URL for the platform to scrape (Outlook, OneDrive, Google Drive, eFundi).",
            "email": "Optional. Defaults to the enrolment e-mail.",
            "year": "Optional. Defaults to the provided payload year or current year.",
            "month": "Optional. Defaults to the provided payload month or current month.",
            "deep_read": "Optional boolean. When false, skips deep content extraction (defaults to true)."
        }
    }
}


def _strip_action_blocks(text: str) -> str:
    """Remove any ```tool``` blocks before returning a final answer."""

    if not text:
        return ""
    return _ACTION_BLOCK.sub("", text).strip()


def _extract_action(text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Return (action_dict, error) parsed from a ```tool``` block, if present."""

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


async def _execute_action(
    action: Dict[str, Any],
    base_msg: Dict[str, Any],
    uid: str,
    *,
    progress_cb: Optional[Callable[[float, str], Awaitable[None]]] = None,
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

    if name != "scan_active":
        observation["error"] = f"Unknown tool: {name}"
        return observation

    if run_scan_active_ws is None:
        observation["error"] = "VAMP agent not available"
        return observation

    # Defaults derived from payload or system state
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
            except Exception as exc:  # pragma: no cover - progress reporting best effort
                logger.debug(f"Progress callback failed: {exc}")

    try:
        results = await run_scan_active_ws(
            email=email,
            year=year,
            month=month,
            url=url,
            deep_read=bool(deep_read),
            progress_callback=capture_progress,
        )
    except Exception as exc:  # pragma: no cover - Playwright errors
        observation["error"] = f"Scan failed: {exc}"
        observation["progress"] = progress_log
        return observation

    results = results or []

    try:
        month_doc = store.add_items(email or uid, year, month, results)
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
    progress_cb: Optional[Callable[[float, str], Awaitable[None]]] = None,
    purpose: str = "ask",
) -> Dict[str, Any]:
    """Drive an LLM loop that can invoke connectors before producing an answer."""

    if not ask_ollama:
        return {"answer": f"[VAMP AI] Received: {question}", "tools": []}

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

    evidence_overview = (
        f"Evidence store for {year}-{month:02d}: {len(existing_items)} items"
    )
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
    context_line = (
        f"User context → email: {email}, year: {year}, month: {month}"
    )

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
            "Example: ```tool\\n{\"tool\":\"scan_active\",\"arguments\":{\"url\":\"https://outlook.office.com/mail/\",\"email\":\"user@nwu.ac.za\"}}\\n```. "
            "After a connector runs, review the tool result from the history and continue reasoning. "
            "When you are ready to respond, provide a concise written answer with citations of the evidence summaries."
        )

    for step in range(max_steps):
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

        response = response or ""
        history.append(("assistant", _strip_action_blocks(response)))

        action, error = _extract_action(response)
        if error:
            error_obs = {"tool": "", "status": "error", "error": error}
            history.append(("tool", json.dumps(error_obs, ensure_ascii=False)))
            tool_summaries.append(error_obs)
            continue

        if action:
            observation = await _execute_action(action, msg, uid, progress_cb=progress_cb)
            tool_summaries.append(observation)
            history.append(("tool", json.dumps(observation, ensure_ascii=False)))
            continue

        final_answer = _strip_action_blocks(response)
        if tool_summaries:
            formatted = "\n".join(
                f"- {obs.get('tool') or 'unknown'} → {obs.get('status')} (items={obs.get('items_found', 0)})"
                for obs in tool_summaries
            )
            final_answer = f"{final_answer}\n\nTools used:\n{formatted}".strip()
        return {"answer": final_answer or "(AI returned no answer)", "tools": tool_summaries}

    # If loop exhausted without final answer, surface last assistant message
    fallback = history[-1][1] if history else "(AI produced no answer)"
    if tool_summaries:
        formatted = "\n".join(
            f"- {obs.get('tool') or 'unknown'} → {obs.get('status')} (items={obs.get('items_found', 0)})"
            for obs in tool_summaries
        )
        fallback = f"{fallback}\n\nTools used:\n{formatted}".strip()
    return {"answer": fallback, "tools": tool_summaries}

# --- Helpers ---
def ok(action: str, data: Any = None) -> str:
    payload = {"ok": True, "action": action}
    if data is not None:
        payload["data"] = data
    return json.dumps(payload)


def fail(action: str, error: Any) -> str:
    msg = str(error) if not isinstance(error, str) else error
    return json.dumps({"ok": False, "action": action, "error": msg})


async def _safe_send(ws: WebSocketServerProtocol, payload: str, action: str) -> bool:
    """Send a payload to the client, gracefully handling disconnections."""

    try:
        await ws.send(payload)
        return True
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Client disconnected while sending {action}")
        return False


def _uid_from(msg: Dict[str, Any]) -> str:
    email = (msg.get("email") or "").strip().lower()
    if email:
        return _uid(email)
    name = (msg.get("name") or "").strip().lower()
    org = (msg.get("org") or "nwu").strip().lower()
    return f"{name}@{org}" if name else "anon@nwu"


# --- Actions ---
async def on_enrol(ws: WebSocketServerProtocol, msg: Dict[str, Any]) -> None:
    email = msg.get("email", "").strip()
    name = msg.get("name", "").strip()
    org = msg.get("org", "NWU").strip()
    if not email:
        await _safe_send(ws, fail("ENROL", "Email required"), "ENROL")
        return
    try:
        profile = store.enroll(email, name, org)
        await _safe_send(ws, ok("ENROL", profile), "ENROL")
        logger.info(f"Enrolled: {email}")
    except Exception as e:
        await _safe_send(ws, fail("ENROL", str(e)), "ENROL")


async def on_get_state(ws: WebSocketServerProtocol, msg: Dict[str, Any]) -> None:
    uid = _uid_from(msg)
    year = int(msg.get("year", 2025))
    try:
        year_doc = store.get_year_doc(uid, year)
        await _safe_send(ws, ok("GET_STATE", {"year_doc": year_doc}), "GET_STATE")
    except Exception as e:
        await _safe_send(ws, fail("GET_STATE", str(e)), "GET_STATE")


async def on_finalise_month(ws: WebSocketServerProtocol, msg: Dict[str, Any]) -> None:
    uid = _uid_from(msg)
    year = int(msg.get("year", 2025))
    month = int(msg.get("month", 11))
    try:
        doc = store.finalise_month(uid, year, month)
        await _safe_send(ws, ok("FINALISE_MONTH", doc), "FINALISE_MONTH")
    except Exception as e:
        await _safe_send(ws, fail("FINALISE_MONTH", str(e)), "FINALISE_MONTH")


async def on_export_month(ws: WebSocketServerProtocol, msg: Dict[str, Any]) -> None:
    uid = _uid_from(msg)
    year = int(msg.get("year", 2025))
    month = int(msg.get("month", 11))
    try:
        path = store.export_month_csv(uid, year, month)
        await _safe_send(ws, ok("EXPORT_MONTH", {"path": str(path)}), "EXPORT_MONTH")
    except Exception as e:
        await _safe_send(ws, fail("EXPORT_MONTH", str(e)), "EXPORT_MONTH")


async def on_compile_year(ws: WebSocketServerProtocol, msg: Dict[str, Any]) -> None:
    uid = _uid_from(msg)
    year = int(msg.get("year", 2025))
    try:
        path = store.export_year_csv(uid, year)
        await _safe_send(ws, ok("COMPILE_YEAR", {"path": str(path)}), "COMPILE_YEAR")
    except Exception as e:
        await _safe_send(ws, fail("COMPILE_YEAR", str(e)), "COMPILE_YEAR")


async def on_scan_active(ws: WebSocketServerProtocol, msg: Dict[str, Any]) -> None:
    if run_scan_active_ws is None:
        await _safe_send(ws, fail("SCAN_ACTIVE", "vamp_agent not available"), "SCAN_ACTIVE")
        return

    email = (msg.get("email") or "").strip().lower()
    uid = _uid(email) if email else _uid_from(msg)
    year = int(msg.get("year", 2025))
    month = int(msg.get("month", 11))
    url = msg.get("url") or "https://outlook.office365.com/mail/"
    deep_read = bool(msg.get("deep_read", True))

    logger.info(f"Starting scan for {uid}, {year}-{month:02d}, url={url}")

    if not await _safe_send(ws, ok("SCAN_ACTIVE/STARTED"), "SCAN_ACTIVE/STARTED"):
        return

    # Progress callback that sends updates over WebSocket
    async def on_progress(progress: float, status: str) -> None:
        pct = float(progress)
        payload = {
            "pct": pct,
            "progress": max(0.0, min(1.0, pct / 100.0)),
            "status": status or "",
        }
        await _safe_send(ws, ok("SCAN_ACTIVE/PROGRESS", payload), "SCAN_ACTIVE/PROGRESS")

    async def _send_complete(added: int, total: int, summary: str, tools: Optional[List[Dict[str, Any]]] = None) -> None:
        payload: Dict[str, Any] = {
            "added": added,
            "total_evidence": total,
        }
        if summary:
            payload["brain_summary"] = summary
        if tools:
            payload["tools"] = tools
        await _safe_send(ws, ok("SCAN_ACTIVE/COMPLETE", payload), "SCAN_ACTIVE/COMPLETE")

    orchestrated: Optional[Dict[str, Any]] = None

    try:
        if ask_ollama:
            brain_msg = dict(msg)
            brain_msg.setdefault("email", email or uid)
            brain_msg.setdefault("year", year)
            brain_msg.setdefault("month", month)
            brain_msg.setdefault("url", url)
            brain_msg.setdefault("deep_read", deep_read)

            scan_question = (
                "Execute the scan_active connector for the provided user context right now. "
                f"Target URL: {url}. Deep read: {'true' if deep_read else 'false'}. "
                "After the connector finishes, summarise the scan outcome, including how many new evidence items were stored."
            )

            orchestrated = await _orchestrate_answer(
                brain_msg,
                scan_question,
                progress_cb=on_progress,
                purpose="scan",
            )

    except Exception as exc:
        logger.warning(f"AI-orchestrated scan failed, falling back: {exc}")
        orchestrated = None

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
                await _send_complete(added, total, summary_text, tool_payload)
                logger.info(f"AI scan complete for {uid}: +{added}, total={total}")
                return

        # Fallback to direct Playwright execution if AI did not produce a tool observation
        results = await run_scan_active_ws(
            email=email or uid,
            year=year,
            month=month,
            url=url,
            deep_read=deep_read,
            progress_callback=on_progress,
        )

        results = results or []
        if not results:
            await on_progress(100.0, "Scan complete — no new items")
            await _send_complete(0, 0, "The scan completed without finding new evidence artefacts.")
            return

        month_doc = store.add_items(uid, year, month, results)
        added = len(results)
        total = len(month_doc.get("items", []))
        summary_text = (
            f"Manual fallback added {added} new evidence items. "
            f"The month now tracks {total} total artefacts."
        )

        fallback_tools = [
            {
                "tool": "scan_active",
                "status": "success",
                "items_found": added,
                "total_month_items": total,
                "mode": "fallback",
            }
        ]

        await on_progress(100.0, "Scan complete")
        await _send_complete(added, total, summary_text, fallback_tools)
        logger.info(f"Fallback scan complete: +{added}, total={total}")

    except websockets.exceptions.ConnectionClosed:
        logger.info("Scan halted — client disconnected during send")
    except Exception as e:
        logger.error("Scan failed: %s", e)
        logger.debug("Scan traceback", exc_info=True)
        record_feedback_tag(
            "scan_failed",
            str(e),
            severity="error",
            context={"uid": uid, "year": year, "month": month, "url": url},
        )
        await _safe_send(ws, fail("SCAN_ACTIVE", str(e)), "SCAN_ACTIVE")


async def on_ask(ws: WebSocketServerProtocol, msg: Dict[str, Any]) -> None:
    messages = msg.get("messages", [])
    question = "\n\n".join(str(m.get("content", "")) for m in messages if isinstance(m, dict)).strip()

    mode = str(msg.get("mode") or "").strip().lower() or "ask"
    is_brain_scan = mode in {"brain_scan", "scan", "scan_via_brain"}

    if is_brain_scan and not question:
        await _safe_send(ws, fail("SCAN_ACTIVE", "No scan request provided"), "SCAN_ACTIVE")
        await _safe_send(ws, ok("ASK", {"answer": "[VAMP AI] No question received.", "mode": mode, "tools": []}), "ASK")
        return

    async def forward_progress(progress: float, status: str) -> None:
        payload = {
            "pct": float(progress),
            "progress": max(0.0, min(1.0, float(progress) / 100.0)),
            "status": status or "",
        }
        await _safe_send(ws, ok("SCAN_ACTIVE/PROGRESS", payload), "SCAN_ACTIVE/PROGRESS")

    if not question:
        await _safe_send(ws, ok("ASK", {"answer": "[VAMP AI] No question received.", "mode": mode, "tools": []}), "ASK")
        return

    if is_brain_scan:
        await _safe_send(ws, ok("SCAN_ACTIVE/STARTED"), "SCAN_ACTIVE/STARTED")

    try:
        orchestration = await _orchestrate_answer(
            msg,
            question,
            progress_cb=forward_progress if is_brain_scan else None,
            purpose="scan" if is_brain_scan else "ask",
        )
    except Exception as exc:
        logger.warning(f"orchestration failed: {exc}")
        if is_brain_scan:
            await _safe_send(ws, fail("SCAN_ACTIVE", str(exc)), "SCAN_ACTIVE")
        fallback = f"[VAMP AI] (fallback) {question}"
        await _safe_send(ws, ok("ASK", {"answer": fallback, "mode": mode, "tools": []}), "ASK")
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
        await _safe_send(ws, ok("SCAN_ACTIVE/COMPLETE", complete_payload), "SCAN_ACTIVE/COMPLETE")

    await _safe_send(ws, ok("ASK", payload), "ASK")


async def on_ask_feedback(ws: WebSocketServerProtocol, msg: Dict[str, Any]) -> None:
    messages = msg.get("messages", [])
    question = "\n\n".join(str(m.get("content", "")) for m in messages if isinstance(m, dict)).strip()

    answer = "[VAMP Assessor] No feedback request received."

    if question:
        if analyze_feedback_with_ollama and HAS_STRUCTURED_FEEDBACK:
            loop = asyncio.get_running_loop()

            def _call_feedback() -> str:
                try:
                    result = analyze_feedback_with_ollama([], [question])  # type: ignore[arg-type]
                except Exception as exc:
                    raise exc

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
            except Exception as e:
                logger.warning(f"analyze_feedback_with_ollama failed: {e}")
                answer = f"[VAMP Assessor] (fallback) {question}"
        elif ask_ollama:
            loop = asyncio.get_running_loop()
            try:
                answer = await loop.run_in_executor(None, partial(ask_ollama, question))
            except Exception as e:
                logger.warning(f"ask_ollama feedback fallback failed: {e}")
                answer = f"[VAMP Assessor] (fallback) {question}"
        else:
            answer = f"[VAMP Assessor] Received: {question}"

    await _safe_send(ws, ok("ASK_FEEDBACK", {"answer": answer}), "ASK_FEEDBACK")


# --- Handler ---
async def handler(ws: WebSocketServerProtocol, path: Optional[str] = None) -> None:
    client_addr = f"{ws.remote_address[0]}:{ws.remote_address[1]}"
    ws_path = path if path is not None else getattr(ws, "path", "/")
    logger.info(f"Client connected: {client_addr} path={ws_path}")
    try:
        async for message in ws:
            try:
                msg = json.loads(message)
                action = msg.get("action", "").upper()

                if action == "ENROL":
                    await on_enrol(ws, msg)
                elif action == "GET_STATE":
                    await on_get_state(ws, msg)
                elif action == "FINALISE_MONTH":
                    await on_finalise_month(ws, msg)
                elif action == "EXPORT_MONTH":
                    await on_export_month(ws, msg)
                elif action == "COMPILE_YEAR":
                    await on_compile_year(ws, msg)
                elif action == "SCAN_ACTIVE":
                    await on_scan_active(ws, msg)
                elif action == "ASK":
                    await on_ask(ws, msg)
                elif action == "ASK_FEEDBACK":
                    await on_ask_feedback(ws, msg)
                else:
                    await _safe_send(ws, fail(action, "Unknown action"), action or "UNKNOWN")

            except json.JSONDecodeError:
                if not await _safe_send(ws, fail("ERROR", "Invalid JSON"), "ERROR"):
                    break
            except Exception as e:
                if not await _safe_send(ws, fail("ERROR", str(e)), "ERROR"):
                    break
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Client disconnected: {client_addr}")
    except Exception as e:
        logger.error(f"Handler error: {e}")


# --- Server ---
async def main_async():
    logger.info(f"Starting VAMP WS Bridge on ws://{APP_HOST}:{APP_PORT}")
    async with websockets.serve(handler, APP_HOST, APP_PORT, ping_interval=20, ping_timeout=20):
        await asyncio.Future()  # Run forever


def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")


if __name__ == "__main__":
    main()
