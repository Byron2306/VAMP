import json
import os
import pathlib
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app_server import create_app
from backend.agent_app import api as api_module
from backend.agent_app.plugin_manager import PluginDefinition


class StubAuthManager:
    def __init__(self, sessions: List[Dict[str, object]]) -> None:
        self.sessions = sessions
        self.stored_passwords: List[Dict[str, object]] = []
        self.events: List[str] = []

    def list_sessions(self) -> List[SimpleNamespace]:
        return list(self.sessions)

    def audit_log(self) -> List[SimpleNamespace]:
        return []

    def refresh_session_state(self, service: str, identity: str, *, state_path: Path, notes: str = "") -> SimpleNamespace:
        entry = {
            "service": service,
            "identity": identity,
            "state_path": str(state_path),
            "refreshed_at": time.time(),
            "status": "ready",
            "notes": notes,
        }
        self.sessions.append(entry)
        return SimpleNamespace(**entry)

    def end_session(self, service: str, identity: str) -> None:
        key = f"{service}:{identity}"
        self.events.append(f"end:{key}")

    def get_session(self, service: str, identity: str) -> SimpleNamespace | None:
        for session in self.sessions:
            if session["service"] == service and session["identity"] == identity:
                return SimpleNamespace(**session)
        return None

    def store_password(self, service: str, identity: str, password: str, *, metadata: Dict[str, str] | None = None) -> None:
        self.stored_passwords.append({"service": service, "identity": identity, "password": password, "metadata": metadata or {}})


class StubEvidenceVault:
    def __init__(self) -> None:
        self.records: List[Dict[str, object]] = []

    def retention_summary(self) -> Dict[str, object]:
        return {"total": len(self.records), "pending_deletion": []}

    def list(self) -> List[SimpleNamespace]:
        return [SimpleNamespace(**record) for record in self.records]

    def record(self, record: SimpleNamespace) -> None:
        self.records.append(record.__dict__)

    def delete(self, uid: str, reason: str = "") -> None:
        self.records = [record for record in self.records if record.get("uid") != uid]


class StubUpdateManager:
    def status(self) -> Dict[str, object]:
        return {"version": "1.0", "status": "idle"}

    def check_for_updates(self) -> Dict[str, object]:
        return {"checked": True}

    def apply_latest(self) -> Dict[str, object]:
        return {"applied": True}

    def rollback(self) -> Dict[str, object]:
        return {"rolled_back": True}


class StubState:
    def __init__(self) -> None:
        self.plugin_definitions = [
            PluginDefinition(
                name="outlook",
                module="backend.platform_plugins.outlook",
                cls="OutlookConnector",
                enabled=True,
                config={"foo": "bar"},
            )
        ]
        self.auth_manager = StubAuthManager([
            {
                "service": "outlook",
                "identity": "user@example.com",
                "state_path": "/tmp/state.json",
                "refreshed_at": 1.0,
                "status": "ready",
                "notes": "",
                "last_audit_event": None,
            }
        ])
        self.evidence_vault = StubEvidenceVault()
        self.update_manager = StubUpdateManager()

    def connectors(self, *, include_disabled: bool = False) -> List[PluginDefinition]:
        if include_disabled:
            return list(self.plugin_definitions)
        return [definition for definition in self.plugin_definitions if definition.enabled]

    def connector_diagnostics(self) -> Dict[str, Dict[str, object]]:
        return {definition.name: {"status": "ok", "enabled": definition.enabled} for definition in self.plugin_definitions}

    def health(self):
        return SimpleNamespace(
            connectors=self.connector_diagnostics(),
            auth_sessions=self.auth_manager.list_sessions(),
            evidence_summary=self.evidence_vault.retention_summary(),
            last_updated=time.time(),
        )

    def enable_connector(self, name: str) -> None:
        for definition in self.plugin_definitions:
            if definition.name == name:
                definition.enabled = True

    def disable_connector(self, name: str) -> None:
        for definition in self.plugin_definitions:
            if definition.name == name:
                definition.enabled = False

    def update_connector_config(self, name: str, config: Dict[str, object]) -> None:
        for definition in self.plugin_definitions:
            if definition.name == name:
                definition.config = config

    def add_connector(self, definition: PluginDefinition) -> None:
        self.plugin_definitions.append(definition)

    def remove_connector(self, name: str) -> None:
        self.plugin_definitions = [definition for definition in self.plugin_definitions if definition.name != name]

    def evidence_records(self) -> List[Dict[str, object]]:
        return list(self.evidence_vault.records)

    def record_evidence(self, record: Dict[str, object]) -> None:
        self.evidence_vault.record(SimpleNamespace(**record))

    def delete_evidence(self, uid: str, reason: str) -> None:
        self.evidence_vault.delete(uid, reason)

    def upgrade_info(self) -> Dict[str, object]:
        return self.update_manager.status()

    def check_for_updates(self) -> Dict[str, object]:
        return self.update_manager.check_for_updates()

    def apply_update(self) -> Dict[str, object]:
        return self.update_manager.apply_latest()

    def rollback(self) -> Dict[str, object]:
        return self.update_manager.rollback()


@pytest.fixture
def client(monkeypatch):
    stub_state = StubState()
    monkeypatch.setattr(api_module, "agent_state", lambda: stub_state)
    app, _ = create_app()
    app.testing = True
    return app.test_client(), stub_state


def test_health_endpoint_reports_stubbed_components(client):
    test_client, stub_state = client
    response = test_client.get("/api/health")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["connectors"]["outlook"]["status"] == "ok"
    assert payload["auth_sessions"] == stub_state.auth_manager.list_sessions()
    assert payload["evidence"]["total"] == 0


def test_connector_lifecycle(client):
    test_client, stub_state = client

    # Disable connector
    resp = test_client.post("/api/connectors/outlook", json={"enabled": False})
    assert resp.status_code == 200
    assert not stub_state.plugin_definitions[0].enabled

    # Update config
    resp = test_client.post("/api/connectors/outlook", json={"config": {"depth": 3}})
    assert resp.status_code == 200
    assert stub_state.plugin_definitions[0].config == {"depth": 3}

    # Add a new connector
    resp = test_client.put(
        "/api/connectors",
        data=json.dumps(
            {
                "name": "drive",
                "module": "backend.platform_plugins.drive",
                "cls": "DriveConnector",
                "enabled": True,
                "config": {},
            }
        ),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert any(defn.name == "drive" for defn in stub_state.plugin_definitions)

    # Remove the connector
    resp = test_client.delete("/api/connectors/drive")
    assert resp.status_code == 200
    assert not any(defn.name == "drive" for defn in stub_state.plugin_definitions)


def test_evidence_crud(client):
    test_client, stub_state = client

    resp = test_client.post(
        "/api/evidence",
        json={
            "uid": "abc123",
            "source": "test",
            "title": "Test evidence",
            "kpas": [1, 2],
            "score": 0.8,
            "rationale": "demo",
            "metadata": {"tag": "x"},
        },
    )
    assert resp.status_code == 200
    assert len(stub_state.evidence_vault.records) == 1

    resp = test_client.get("/api/evidence")
    payload = resp.get_json()
    assert payload["records"][0]["uid"] == "abc123"

    resp = test_client.delete("/api/evidence/abc123")
    assert resp.status_code == 200
    assert stub_state.evidence_vault.records == []


def test_session_refresh_path_and_staleness_warning(client, tmp_path, monkeypatch):
    test_client, _ = client

    state_path = tmp_path / "state.json"
    state_path.write_text("{}", encoding="utf-8")
    old_time = time.time() - (9 * 86400)
    os.utime(state_path, (old_time, old_time))

    response = test_client.post(
        "/api/auth/session/refresh",
        json={"service": "outlook", "identity": "tester", "state_path": str(state_path)},
    )
    payload = response.get_json()
    assert payload["status"] == "warning"
    assert payload["state_path"] == str(state_path)


def test_update_endpoints(client):
    test_client, stub_state = client

    assert test_client.get("/api/updates/status").get_json() == stub_state.update_manager.status()
    assert test_client.post("/api/updates/check").get_json() == stub_state.update_manager.check_for_updates()
    assert test_client.post("/api/updates/apply").get_json() == stub_state.update_manager.apply_latest()
    assert test_client.post("/api/updates/rollback").get_json() == stub_state.update_manager.rollback()
