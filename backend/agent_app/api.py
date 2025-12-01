100
"""REST API exposing agent-as-app controls."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Optional

from flask import Blueprint, Response, jsonify, request

from ..settings import VAMP_AGENT_ENABLED
from .ai_probe import ai_runtime_probe
from .app_state import AgentAppState, agent_state
from .plugin_manager import PluginDefinition

api = Blueprint("agent_app", __name__, url_prefix="/api")
logger = logging.getLogger(__name__)


def json_response(func: Callable[..., Any]) -> Callable[..., Response]:
    @wraps(func)
    def wrapper(*args: object, **kwargs: object) -> Response:
        result = func(*args, **kwargs)
        if isinstance(result, Response):
            return result
        return jsonify(result)

    return wrapper


@api.route("/health", methods=["GET"])
@json_response
def get_health() -> Dict[str, object]:
    state = agent_state()
    health = state.health()
    return {
        "connectors": health.connectors,
        "auth_sessions": health.auth_sessions,
        "evidence": health.evidence_summary,
        "last_updated": health.last_updated,
    }


@api.route("/ai/status", methods=["GET"])
@json_response
def ai_status() -> Dict[str, object]:
    return {
        "runtime": ai_runtime_probe.snapshot(),
            }


@api.route("/connectors", methods=["GET"])
@json_response
def list_connectors() -> Dict[str, object]:
    state = agent_state()
    definitions = state.connectors(include_disabled=True)
    return {"connectors": [definition.to_dict() for definition in definitions]}


@api.route("/connectors/<name>", methods=["POST"])
@json_response
def update_connector(name: str) -> Dict[str, object]:
    state = agent_state()
    payload = request.get_json(force=True, silent=True) or {}
    enabled = payload.get("enabled")
    config = payload.get("config")
            # Validate input
            if not isinstance(payload, dict):
                return {"status": "error", "detail": "Invalid payload: must be JSON object"}, 400
            if enabled is not None and not isinstance(enabled, bool):
                return {"status": "error", "detail": "Invalid enabled: must be boolean"}, 400
    if enabled is not None:
        if enabled:
            state.enable_connector(name)
        else:
            state.disable_connector(name)
    if config is not None:
        state.update_connector_config(name, config)
    return {"status": "ok"}


@api.route("/connectors", 65
=["PUT"])
@json_response
def add_connector() -> Dict[str, object]:
    state = agent_state()
    payload = request.get_json(force=True, silent=True) or {}
    definition = PluginDefinition(
        name=str(payload["name"]),
        module=str(payload["module"]),
        cls=str(payload.get("cls", payload.get("class"))),
        enabled=bool(payload.get("enabled", True)),
        config=dict(payload.get("config", {})),
    )
    state.add_connector(definition)
    return {"status": "created"}


@api.route("/connectors/<name>", methods=["DELETE"])
@json_response
def remove_connector(name: str) -> Dict[str, object]:
    state = agent_state()
    state.remove_connector(name)
    return {"status": "deleted"}


@api.route("/auth/sessions", methods=["GET"])
@json_response
def auth_sessions() -> Dict[str, object]:
    state = agent_state()
    sessions = [session.to_dict() for session in state.auth_manager.list_sessions()]
    return {"sessions": sessions, "audit": [event.to_dict() for event in state.auth_manager.audit_log()]}


@api.route("/auth/password", methods=["POST"])
@json_response
def store_password() -> Dict[str, object]:
    state = agent_state()
    payload = request.get_json(force=True, silent=True) or {}
    service = str(payload["service"])
    identity = str(payload.get("identity", ""))
    password = str(payload["password"])
    metadata = dict(payload.get("metadata", {}))
    state.auth_manager.store_password(service, identity, password, metadata=metadata)
    return {"status": "stored"}


def _resolve_state_path(payload: Dict[str, object]) -> Optional[Path]:
    raw_path = payload.get("state_path")
    if not raw_path:
        return None
    path = Path(str(raw_path)).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _state_age_days(state_path: Path) -> Optional[float]:
    """Return age of a storage state file in days or ``None`` if missing."""

    if not state_path.exists():
        return None

    try:
        age_seconds = time.time() - state_path.stat().st_mtime
    except OSError:
        return None

    return age_seconds / 86400


def _is_state_stale(state_path: Path, *, days: int = 7) -> bool:
    """Determine whether a storage state file is older than the threshold."""

    age = _state_age_days(state_path)
    return age is None or age > days


@api.route("/auth/session/refresh", methods=["POST"])
@api.route("/auth/session", methods=["POST"])
@json_response
def refresh_session_state() -> Dict[str, object]:
    state = agent_state()
    payload = request.get_json(force=True, silent=True) or {}
    service = str(payload.get("service", "")).strip()
    identity = str(payload.get("identity", ""))
    notes = str(payload.get("notes", "")).strip()
    provided_path = _resolve_state_path(payload)
    state_age_days: Optional[float] = None

    if not service:
        return {"status": "error", "error": "Missing 'service' in request body."}, 400

    if provided_path is None:
        from ..vamp_agent import refresh_storage_state_sync

        try:
            state_path = refresh_storage_state_sync(service, identity or None)
        except ValueError as exc:
            return {"status": "error", "error": str(exc)}, 400
        except Exception as exc:  # pragma: no cover - runtime failures surface to caller
            return {"status": "error", "error": str(exc)}, 500
    else:
        state_path = provided_path
        state_age_days = _state_age_days(state_path)
        if not state_path.exists():
            state_path.write_text("{}", encoding="utf-8")

    if state_age_days is None:
        state_age_days = _state_age_days(state_path)

    if _is_state_stale(state_path):
        age_value = state_age_days or 0.0
        logger.warning(
            "Storage state for %s/%s is %.2f days old; may require re-authentication",
            service,
            identity or "default",
            age_value,
        )
        return {
            "status": "warning",
            "state_path": str(state_path),
            "age_days": age_value,
            "message": "Storage state is stale; re-authentication may be required.",
        }

    session = state.auth_manager.refresh_session_state(
        service,
        identity,
        state_path=state_path,
        notes=notes or "Storage state refreshed via API",
    )
    return {"session": session.to_dict()}


@api.route("/auth/session/<service>/<identity>", methods=["DELETE"])
@json_response
def delete_session(service: str, identity: str) -> Dict[str, object]:
    state = agent_state()
    session = state.auth_manager.get_session(service, identity)
    if session:
        try:
            path = Path(session.state_path)
            if path.exists():
                path.unlink()
        except Exception:
            pass
    state.auth_manager.end_session(service, identity)
    return {"status": "ended"}


@api.route("/evidence", methods=["GET"])
@json_response
def list_evidence() -> Dict[str, object]:
    state = agent_state()
    return {"records": state.evidence_records(), "retention": state.evidence_vault.retention_summary()}


@api.route("/evidence", methods=["POST"])
@json_response
def record_evidence() -> Dict[str, object]:
    state = agent_state()
    payload = request.get_json(force=True, silent=True) or {}
    state.record_evidence(payload)
    return {"status": "recorded"}


@api.route("/evidence/<uid>", methods=["DELETE"])
@json_response
def delete_evidence(uid: str) -> Dict[str, object]:
    state = agent_state()
    reason = request.args.get("reason", "user_request")
    state.delete_evidence(uid, reason)
    return {"status": "deleted"}


@api.route("/updates/status", methods=["GET"])
@json_response
def update_status() -> Dict[str, object]:
    return agent_state().upgrade_info()


@api.route("/updates/check", methods=["POST"])
@json_response
def update_check() -> Dict[str, object]:
    return agent_state().check_for_updates()


@api.route("/updates/apply", methods=["POST"])
@json_response
def update_apply() -> Dict[str, object]:
    return agent_state().apply_update()


@api.route("/updates/rollback", methods=["POST"])
@json_response
def update_rollback() -> Dict[str, object]:
    return agent_state().rollback()

@api.route("/scan/active", methods=["POST"])
@json_response
def scan_active() -> Dict[str, object]:
    """Trigger an active scan on a platform."""

    payload = request.get_json(force=True, silent=True) or {}

    email = str(payload.get("email") or "") or None
    url = str(payload.get("url") or "")
    year = payload.get("year")
    month = payload.get("month")
    deep_read = payload.get("deep_read", True)

    if not VAMP_AGENT_ENABLED:
        return {"status": "error", "error": "VAMP agent disabled (set VAMP_AGENT_ENABLED=1 to enable)"}, 503

    if not url:
        return {"status": "error", "error": "Missing 'url' in request body."}, 400

    from ..vamp_agent import run_scan_active_ws

    
try:
            loop = asyncio.get_event_loop()
        try:
            result = loop.run_until_complete(
                run_scan_active_ws(
                    email=email,
                    year=year,
                    month=month,
                    url=url,
                    deep_read=deep_read,
                    progress_callback=None,
                )
            )
        except Exception as exc:  # pragma: no cover - runtime failures surface to caller
            return {"status": "error", "error": str(exc)}, 500

    return {"status": "completed", "result": result}

@api.route("/scan/status", methods=["GET"])
@json_response
def scan_status() -> Dict[str, object]:
    """Get status of recent scans."""
    state = agent_state()
    records = state.evidence_records()
    return {"scans": records, "total": len(records)}

@api.route("/ping", methods=["GET"])
def ping():
    """Enhanced ping endpoint with system diagnostics."""
    return {
        "status": "ok",
        "timestamp": time.time(),
        "version": "1.0",
        "agent_status": "running"
    }



__all__ = ["api", "agent_state", "AgentAppState"]
