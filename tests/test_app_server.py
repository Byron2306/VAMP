from __future__ import annotations

import os
import pathlib
import sys

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app_server import create_app
from backend.vamp_store import VampStore


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
