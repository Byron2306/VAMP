from __future__ import annotations

import json
import os
import pathlib
import sys
import time

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app_server import create_app
from backend.vamp_store import VampStore


@pytest.fixture(autouse=True)
def isolate_agent_runtime(monkeypatch, tmp_path):
    """Keep agent-app state in a per-test sandbox.

    The agent runtime writes connector configs, auth sessions, secrets, and
    evidence logs to disk. To keep tests hermetic (and avoid touching the
    repository's checked-in data), redirect every agent-app path to the pytest
    ``tmp_path`` sandbox and reset the AgentAppState singleton between tests.
    """

    agent_root = tmp_path / "agent_runtime"
    state_dir = agent_root / "state"
    config_dir = agent_root / "config"
    log_dir = state_dir / "logs"
    for path in (state_dir, config_dir, log_dir):
        path.mkdir(parents=True, exist_ok=True)

    import backend.agent_app as agent_app_pkg
    monkeypatch.setattr(agent_app_pkg, "AGENT_STATE_DIR", state_dir, raising=False)
    monkeypatch.setattr(agent_app_pkg, "AGENT_CONFIG_DIR", config_dir, raising=False)
    monkeypatch.setattr(agent_app_pkg, "AGENT_LOG_DIR", log_dir, raising=False)

    import backend.agent_app.secrets_vault as secrets_vault
    monkeypatch.setattr(secrets_vault, "AGENT_STATE_DIR", state_dir, raising=False)
    monkeypatch.setattr(secrets_vault, "VAULT_FILE", state_dir / "secrets.json", raising=False)
    monkeypatch.setattr(secrets_vault, "KEY_FILE", state_dir / "secrets.key", raising=False)
    monkeypatch.setattr(
        secrets_vault.SecretsVault,
        "default",
        classmethod(
            lambda cls, path=state_dir / "secrets.json", key_path=state_dir / "secrets.key": cls(path=path, key_path=key_path)
        ),
    )

    import backend.agent_app.auth_manager as auth_manager
    monkeypatch.setattr(auth_manager, "AGENT_STATE_DIR", state_dir, raising=False)
    monkeypatch.setattr(auth_manager, "AGENT_LOG_DIR", log_dir, raising=False)
    monkeypatch.setattr(auth_manager, "AUTH_STATE_FILE", state_dir / "auth_sessions.json", raising=False)
    monkeypatch.setattr(
        auth_manager.AuthManager,
        "default",
        classmethod(lambda cls, audit_file=log_dir / "auth.log": cls(audit_file=audit_file)),
    )

    import backend.agent_app.evidence_store as evidence_store
    monkeypatch.setattr(evidence_store, "AGENT_STATE_DIR", state_dir, raising=False)
    monkeypatch.setattr(evidence_store, "AGENT_LOG_DIR", log_dir, raising=False)
    monkeypatch.setattr(evidence_store, "EVIDENCE_FILE", state_dir / "evidence_store.json", raising=False)
    monkeypatch.setattr(evidence_store, "EVIDENCE_LOG", log_dir / "evidence.log", raising=False)
    monkeypatch.setattr(
        evidence_store.EvidenceVault,
        "default",
        classmethod(
            lambda cls,
            store_file=state_dir / "evidence_store.json",
            log_file=log_dir / "evidence.log": cls(store_file=store_file, log_file=log_file)
        ),
    )

    import backend.agent_app.plugin_manager as plugin_manager
    monkeypatch.setattr(plugin_manager, "CONFIG_FILE", config_dir / "platform_config.json", raising=False)
    monkeypatch.setattr(
        plugin_manager.PluginManager,
        "default",
        classmethod(lambda cls, config_file=config_dir / "platform_config.json": cls(config_file=config_file)),
    )

    import backend.agent_app.update_manager as update_manager
    monkeypatch.setattr(update_manager, "AGENT_STATE_DIR", state_dir, raising=False)
    monkeypatch.setattr(update_manager, "STATUS_FILE", state_dir / "update_status.json", raising=False)
    monkeypatch.setattr(
        update_manager.UpdateManager,
        "default",
        classmethod(lambda cls, state_file=state_dir / "update_status.json": cls(state_file=state_file)),
    )

    import backend.agent_app.ai_probe as ai_probe
    ai_probe.ai_runtime_probe.reset()

    import backend.agent_app.app_state as app_state
    app_state._SINGLETON = None

    try:
        yield
    finally:
        app_state._SINGLETON = None


@pytest.fixture(autouse=True)
def temp_store(monkeypatch, tmp_path):
    store_dir = tmp_path / "store"
    monkeypatch.setenv("VAMP_STORE_DIR", str(store_dir))
    yield
    monkeypatch.delenv("VAMP_STORE_DIR", raising=False)


def _drain_responses(test_client):
    received = test_client.get_received()
    return [event['args'][0] for event in received if event['name'] == 'response']


def test_ping_endpoint():
    app, _ = create_app()
    client = app.test_client()
    response = client.get('/api/ping')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["state"]


def test_ai_status_endpoint_reports_brain_and_endpoint():
    app, _ = create_app()
    client = app.test_client()
    response = client.get('/api/ai/status')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["backend"]["brain"]["asset_count"] > 0
    assert payload["backend"]["brain"]["system_prompt_bytes"] > 0
    assert payload["runtime"]["connected_clients"] == 0


def test_websocket_message_roundtrip():
    app, socketio = create_app()
    flask_client = app.test_client()
    test_client = socketio.test_client(app, flask_test_client=flask_client)

    try:
        assert test_client.is_connected()
        _drain_responses(test_client)

        # Emit a message and ensure the bridge echoes it back
        message_payload = {"action": "GET_STATE", "year": 2025}
        test_client.emit('message', message_payload)

        response_events = _drain_responses(test_client)
        assert response_events, "No response event received"

        response_data = response_events[-1]
        assert response_data["ok"] is True
        assert response_data["action"] == "GET_STATE"
        assert "data" in response_data
        assert response_data["data"]["year_doc"]["year"] == 2025
        assert response_data["data"]["year_doc"].get("total_items", 0) == 0

        status_payload = flask_client.get('/api/ai/status').get_json()
        assert status_payload["runtime"]["last_action"]["action"] == "GET_STATE"
        assert status_payload["runtime"]["connected_clients"] >= 1
    finally:
        test_client.disconnect()


def test_websocket_rejects_unknown_actions():
    app, socketio = create_app()
    flask_client = app.test_client()
    test_client = socketio.test_client(app, flask_test_client=flask_client)

    try:
        assert test_client.is_connected()
        _drain_responses(test_client)

        malicious_payload = {"action": "UNKNOWN", "foo": "bar"}

        test_client.emit('message', malicious_payload)

        response_events = _drain_responses(test_client)
        assert response_events, "No response event received"

        response_data = response_events[-1]
        assert response_data == {
            'ok': False,
            'action': 'UNKNOWN',
            'error': 'unsupported_action',
        }
    finally:
        test_client.disconnect()


def test_websocket_enrol_roundtrip():
    app, socketio = create_app()
    flask_client = app.test_client()
    test_client = socketio.test_client(app, flask_test_client=flask_client)

    try:
        assert test_client.is_connected()
        _drain_responses(test_client)

        payload = {
            "action": "ENROL",
            "email": "unit@test.invalid",
            "name": "Unit Test",
            "org": "QA",
        }

        test_client.emit('message', payload)

        response_events = _drain_responses(test_client)
        assert response_events, "Expected enrol response"

        response_data = response_events[-1]
        assert response_data['ok'] is True
        assert response_data['action'] == 'ENROL'
        assert response_data['data']['email'] == 'unit@test.invalid'
    finally:
        test_client.disconnect()


def test_get_state_includes_items_from_session_context():
    store_dir = os.environ["VAMP_STORE_DIR"]
    store = VampStore(store_dir)
    email = "brain@test.invalid"
    store.enroll(email, "Brain Test", "QA")
    store.add_items(
        email,
        2025,
        11,
        [
            {
                "source": "outlook",
                "title": "Evidence Item",
                "hash": "abc123456789",
                "score": 4.2,
            }
        ],
    )

    app, socketio = create_app()
    flask_client = app.test_client()
    test_client = socketio.test_client(app, flask_test_client=flask_client)

    try:
        assert test_client.is_connected()
        _drain_responses(test_client)

        test_client.emit(
            'message',
            {"action": "ENROL", "email": email, "name": "Brain Test", "org": "QA"},
        )
        _drain_responses(test_client)

        test_client.emit('message', {"action": "GET_STATE", "year": 2025})
        responses = _drain_responses(test_client)
        assert responses, "Expected GET_STATE response"

        state_payload = responses[-1]
        assert state_payload["ok"] is True
        months = state_payload["data"]["year_doc"].get("months", {})
        assert "11" in months
        month_payload = months["11"]
        assert len(month_payload.get("items", [])) == 1
        assert month_payload.get("items", [])[0]["title"] == "Evidence Item"
    finally:
        test_client.disconnect()


def test_health_endpoint_reports_connectors():
    app, _ = create_app()
    client = app.test_client()

    response = client.get('/api/health')
    assert response.status_code == 200
    payload = response.get_json()
    assert "connectors" in payload
    assert "outlook" in payload["connectors"]
    assert payload["connectors"]["outlook"]["status"] in {"ready", "not_loaded", "error"}


def test_connector_management_cycle():
    app, _ = create_app()
    client = app.test_client()

    definition = {
        "name": "unit-connector",
        "module": "backend.platform_plugins.outlook",
        "cls": "OutlookConnector",
        "enabled": True,
        "config": {"region": "za"},
    }

    create_resp = client.put('/api/connectors', json=definition)
    assert create_resp.status_code == 200
    assert create_resp.get_json() == {"status": "created"}

    listing = client.get('/api/connectors').get_json()
    connectors = {item["name"]: item for item in listing["connectors"]}
    assert "unit-connector" in connectors
    assert connectors["unit-connector"]["config"] == {"region": "za"}

    disable_resp = client.post('/api/connectors/unit-connector', json={"enabled": False})
    assert disable_resp.get_json() == {"status": "ok"}

    listing = client.get('/api/connectors').get_json()
    connectors = {item["name"]: item for item in listing["connectors"]}
    assert connectors["unit-connector"]["enabled"] is False

    enable_resp = client.post(
        '/api/connectors/unit-connector', json={"enabled": True, "config": {"region": "eu", "env": "test"}}
    )
    assert enable_resp.get_json() == {"status": "ok"}

    listing = client.get('/api/connectors').get_json()
    connectors = {item["name"]: item for item in listing["connectors"]}
    assert connectors["unit-connector"]["enabled"] is True
    assert connectors["unit-connector"]["config"] == {"region": "eu", "env": "test"}

    delete_resp = client.delete('/api/connectors/unit-connector')
    assert delete_resp.get_json() == {"status": "deleted"}

    listing = client.get('/api/connectors').get_json()
    connectors = {item["name"]: item for item in listing["connectors"]}
    assert "unit-connector" not in connectors


def test_auth_session_flow_and_listing():
    app, _ = create_app()
    client = app.test_client()

    payload = {
        "service": "outlook",
        "identity": "agent@test.invalid",
        "access_token": "token123",
        "refresh_token": "refresh456",
        "expires_in": 60,
        "scopes": ["Mail.Read"],
        "metadata": {"source": "unit-test"},
    }

    create_resp = client.post('/api/auth/session', json=payload)
    assert create_resp.status_code == 200
    session = create_resp.get_json()["session"]
    assert session["service"] == "outlook"
    assert session["identity"] == "agent@test.invalid"

    list_resp = client.get('/api/auth/sessions')
    sessions_payload = list_resp.get_json()
    assert sessions_payload["sessions"]
    assert sessions_payload["sessions"][0]["service"] == "outlook"
    assert sessions_payload["audit"]

    delete_resp = client.delete('/api/auth/session/outlook/agent@test.invalid')
    assert delete_resp.get_json() == {"status": "ended"}

    list_resp = client.get('/api/auth/sessions')
    assert list_resp.get_json()["sessions"] == []


def test_evidence_crud_cycle():
    app, _ = create_app()
    client = app.test_client()

    record = {
        "uid": "evidence-1",
        "source": "outlook",
        "title": "Risk event",
        "kpas": [1, 3],
        "score": 9.1,
        "rationale": "Unit test payload",
        "metadata": {"org": "QA"},
    }

    create_resp = client.post('/api/evidence', json=record)
    assert create_resp.get_json() == {"status": "recorded"}

    list_resp = client.get('/api/evidence')
    payload = list_resp.get_json()
    assert payload["records"]
    assert payload["records"][0]["uid"] == "evidence-1"
    assert payload["retention"]["total"] == 1

    delete_resp = client.delete('/api/evidence/evidence-1')
    assert delete_resp.get_json() == {"status": "deleted"}

    list_resp = client.get('/api/evidence')
    payload = list_resp.get_json()
    assert payload["records"] == []
    assert payload["retention"]["total"] == 0


def test_updates_check_apply_and_rollback(monkeypatch, tmp_path):
    feed_path = tmp_path / "feed.json"
    feed_path.write_text(json.dumps([{"version": "1.2.3", "release_notes": "Fixes", "download_url": "https://example"}]))

    monkeypatch.setenv("VAMP_UPDATE_FEED", str(feed_path))
    monkeypatch.setenv("VAMP_INSTALLED_VERSION", "1.0.0")

    app, _ = create_app()
    client = app.test_client()

    status = client.get('/api/updates/status').get_json()
    assert status["installed_version"] in {"0.0.0", "1.0.0"}

    check = client.post('/api/updates/check').get_json()
    assert check["message"] in {"update_available", "up_to_date"}

    if check["message"] == "update_available":
        apply_resp = client.post('/api/updates/apply').get_json()
        assert apply_resp == {"message": "updated", "version": "1.2.3"}

        rollback_resp = client.post('/api/updates/rollback').get_json()
        assert rollback_resp["message"] in {"rolled_back", "no_rollback"}


def test_ask_returns_friendly_fallback_when_llm_fails(monkeypatch):
    import backend.agent_app.ws_dispatcher as ws_dispatcher

    monkeypatch.setattr(ws_dispatcher, "ask_ollama", lambda prompt: "(AI error) Unexpected response format")

    app, socketio = create_app()
    flask_client = app.test_client()
    test_client = socketio.test_client(app, flask_test_client=flask_client)

    try:
        assert test_client.is_connected()
        _drain_responses(test_client)

        payload = {
            "action": "ASK",
            "year": 2025,
            "month": 11,
            "messages": [{"role": "user", "content": "hello"}],
            "mode": "ask",
        }

        test_client.emit('message', payload)
        time.sleep(0.1)
        responses = _drain_responses(test_client)
        ask_payload = next((item for item in responses if item.get("action") == "ASK"), None)
        assert ask_payload, f"ASK response missing: {responses}"
        answer = ask_payload["data"]["answer"]

        assert "(AI error)" not in answer
        assert "hello" in answer.lower()
        assert ask_payload["data"].get("tools") == []
    finally:
        test_client.disconnect()


def test_ask_feedback_uses_basic_response_without_llm(monkeypatch):
    import backend.agent_app.ws_dispatcher as ws_dispatcher

    monkeypatch.setattr(ws_dispatcher, "ask_ollama", lambda prompt: "(AI error) Unexpected response format")
    monkeypatch.setattr(ws_dispatcher, "analyze_feedback_with_ollama", None)

    app, socketio = create_app()
    flask_client = app.test_client()
    test_client = socketio.test_client(app, flask_test_client=flask_client)

    try:
        assert test_client.is_connected()
        _drain_responses(test_client)

        payload = {
            "action": "ASK_FEEDBACK",
            "messages": [{"role": "user", "content": "Please assess."}],
        }

        test_client.emit('message', payload)
        time.sleep(0.1)
        responses = _drain_responses(test_client)
        feedback_payload = next((item for item in responses if item.get("action") == "ASK_FEEDBACK"), None)
        assert feedback_payload, f"ASK_FEEDBACK response missing: {responses}"
        answer = feedback_payload["data"]["answer"]

        assert "(AI error)" not in answer
        assert "assess" in answer.lower()
    finally:
        test_client.disconnect()
