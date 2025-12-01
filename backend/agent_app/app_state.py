
"""Centralised application state for the agent-as-app runtime."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .auth_manager import AuthManager
from .evidence_store import EvidenceVault
from .plugin_manager import PluginDefinition, PluginManager
from .update_manager import UpdateManager

@dataclass
class HealthStatus:
    connectors: Dict[str, Dict[str, object]] = field(default_factory=dict)
    auth_sessions: List[Dict[str, object]] = field(default_factory=list)
    evidence_summary: Dict[str, object] = field(default_factory=dict)
    last_updated: float = field(default_factory=time.time)


class AgentAppState:
    """Facade object exposing the current state of the agent-as-app runtime."""

    def __init__(self) -> None:
        self.auth_manager = AuthManager.default()
        self.plugin_manager = PluginManager.default()
        self.evidence_vault = EvidenceVault.default()
        self.update_manager = UpdateManager.default()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def connectors(self, include_disabled: bool = False) -> List[PluginDefinition]:
        return self.plugin_manager.connectors(include_disabled=include_disabled)

    def connector_diagnostics(self) -> Dict[str, Dict[str, object]]:
        out: Dict[str, Dict[str, object]] = {}
        for definition in self.plugin_manager.connectors(include_disabled=True):
            connector = self.plugin_manager.get_connector(definition.name)
            if connector is None:
                out[definition.name] = {
                    "enabled": definition.enabled,
                    "status": "disabled" if not definition.enabled else "not_loaded",
                }
                continue
            try:
                diag = connector.diagnostics()
                
            except Exception as exc:
                diag = {"status": "error", "detail": str(exc)}
            diag["enabled"] = definition.enabled
            out[definition.name] = diag
        return out

    def health(self) -> HealthStatus:
        with self._lock:
            status = HealthStatus()
            status.connectors = self.connector_diagnostics()
            status.auth_sessions = [session.to_dict() for session in self.auth_manager.list_sessions()]
            status.evidence_summary = self.evidence_vault.retention_summary()
            status.last_updated = time.time()
            return status

    def enable_connector(self, name: str) -> None:
        with self._lock:
            self.plugin_manager.enable(name)

    def disable_connector(self, name: str) -> None:
        with self._lock:
            self.plugin_manager.disable(name)

    def update_connector_config(self, name: str, config: Dict[str, object]) -> None:
        with self._lock:
            self.plugin_manager.update_config(name, config)

    def add_connector(self, definition: PluginDefinition) -> None:
        with self._lock:
            self.plugin_manager.add_connector(definition)

    def remove_connector(self, name: str) -> None:
        with self._lock:
            self.plugin_manager.remove_connector(name)

    def evidence_records(self) -> List[Dict[str, object]]:
        return [record.to_dict() for record in self.evidence_vault.list()]

    def record_evidence(self, record: Dict[str, object]) -> None:
        from .evidence_store import EvidenceRecord

        evidence = EvidenceRecord.from_dict(record)
        self.evidence_vault.record(evidence)

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


_SINGLETON: Optional[AgentAppState] = None


def agent_state() -> AgentAppState:
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = AgentAppState()
    return _SINGLETON


__all__ = ["AgentAppState", "agent_state", "HealthStatus"]
