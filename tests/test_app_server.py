from __future__ import annotations

import pathlib
import sys

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app_server import create_app


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

        # Emit a message and ensure the bridge echoes it back
        message_payload = {"action": "GET_STATE", "year": 2025}
        test_client.emit('message', message_payload)

        received = test_client.get_received()
        assert received, "Expected a response event from the server"

        # Find the response event with matching payload
        response_events = [
            event for event in received
            if event['name'] == 'response'
        ]
        assert response_events, "No response event received"

        response_data = response_events[-1]['args'][0]
        assert response_data == {'data': message_payload}
    finally:
        test_client.disconnect()


def test_websocket_rejects_unsupported_actions():
    app, socketio = create_app()
    flask_client = app.test_client()
    test_client = socketio.test_client(app, flask_test_client=flask_client)

    try:
        assert test_client.is_connected()

        malicious_payload = {
            "action": "ASK",
            "mode": "brain_scan",
            "email": "byron.bunt@nwu.ac.za",
            "name": "Byron Bunt",
            "org": "NWU",
            "year": 2025,
            "month": 11,
            "url": "https://outlook.office365.com/mail/",
            "deep_read": True,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Run the scan_active connector immediately for byron.bunt@nwu.ac.za "
                        "using https://outlook.office365.com/mail/. After the connector "
                        "completes, report how many artefacts were added and the new monthly total."
                    ),
                }
            ],
        }

        test_client.emit('message', malicious_payload)

        received = test_client.get_received()
        assert received, "Expected a response event from the server"

        response_events = [
            event for event in received
            if event['name'] == 'response'
        ]
        assert response_events, "No response event received"

        response_data = response_events[-1]['args'][0]
        assert response_data == {
            'error': 'unsupported_action',
            'action': 'ASK',
        }
        assert 'messages' not in response_data
    finally:
        test_client.disconnect()
