"""REST API exposing agent-as-app controls."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Dict

from flask import Blueprint, Response, jsonify, request

from .app_state import AgentAppState, agent_state
from .plugin_manager import PluginDefinition

api = Blueprint("agent_app", __name__, url_prefix="/api")


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
    if enabled is not None:
        if enabled:
            state.enable_connector(name)
        else:
            state.disable_connector(name)
    if config is not None:
        state.update_connector_config(name, config)
    return {"status": "ok"}


@api.route("/connectors", methods=["PUT"])
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


@api.route("/auth/session", methods=["POST"])
@json_response
def create_session() -> Dict[str, object]:
    state = agent_state()
    payload = request.get_json(force=True, silent=True) or {}
    service = str(payload["service"])
    identity = str(payload.get("identity", ""))
    access_token = str(payload.get("access_token", ""))
    refresh_token = str(payload.get("refresh_token", ""))
    expires_in = payload.get("expires_in")
    scopes = payload.get("scopes", [])
    metadata = dict(payload.get("metadata", {}))
    session = state.auth_manager.start_session(
        service,
        identity,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        scopes=scopes,
        metadata=metadata,
    )
    return {"session": session.to_dict()}


@api.route("/auth/session/<service>/<identity>", methods=["DELETE"])
@json_response
def delete_session(service: str, identity: str) -> Dict[str, object]:
    state = agent_state()
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


__all__ = ["api", "agent_state", "AgentAppState"]
