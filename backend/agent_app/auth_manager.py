"""Authentication/session storage for the VAMP agent app."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from . import AGENT_LOG_DIR, AGENT_STATE_DIR
from .secrets_vault import SecretsVault

logger = logging.getLogger(__name__)

AUTH_STATE_FILE = AGENT_STATE_DIR / "auth_sessions.json"


@dataclass
class AuthEvent:
    timestamp: float
    service: str
    identity: str
    action: str
    detail: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "service": self.service,
            "identity": self.identity,
            "action": self.action,
            "detail": self.detail,
        }


@dataclass
class AuthSession:
    """Represents a captured browser session state managed by the agent."""

    service: str
    identity: str
    state_path: str
    refreshed_at: float
    status: str = "ready"
    notes: str = ""
    last_audit_event: Optional[float] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "service": self.service,
            "identity": self.identity,
            "state_path": self.state_path,
            "refreshed_at": self.refreshed_at,
            "status": self.status,
            "notes": self.notes,
            "last_audit_event": self.last_audit_event,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "AuthSession":
        return cls(
            service=str(data["service"]),
            identity=str(data.get("identity", "")),
            state_path=str(data.get("state_path", "")),
            refreshed_at=float(data.get("refreshed_at", 0.0)),
            status=str(data.get("status", "ready")),
            notes=str(data.get("notes", "")),
            last_audit_event=data.get("last_audit_event"),
        )


class AuthManager:
    """Central orchestrator for Playwright session state (no OAuth)."""

    def __init__(self, vault: Optional[SecretsVault] = None, audit_file: Path = AGENT_LOG_DIR / "auth.log") -> None:
        self.vault = vault or SecretsVault.default()
        self.audit_file = audit_file
        self._sessions: Dict[str, AuthSession] = {}
        self._lock = threading.Lock()
        self._load_sessions()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load_sessions(self) -> None:
        if not AUTH_STATE_FILE.exists():
            return
        try:
            data = json.loads(AUTH_STATE_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load auth sessions: %s", exc)
            return
        sessions = data.get("sessions", []) if isinstance(data, dict) else []
        for raw in sessions:
            try:
                session = AuthSession.from_dict(raw)
            except Exception:
                continue
            key = self._session_key(session.service, session.identity)
            self._sessions[key] = session

    def _persist_sessions(self) -> None:
        payload = {"sessions": [session.to_dict() for session in self._sessions.values()]}
        AUTH_STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _session_key(service: str, identity: str) -> str:
        return f"{service}:{identity or 'default'}"

    # ------------------------------------------------------------------
    # Event logging
    # ------------------------------------------------------------------
    def _log_event(self, event: AuthEvent) -> None:
        line = json.dumps(event.to_dict())
        with self.audit_file.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        session = self._sessions.get(self._session_key(event.service, event.identity))
        if session:
            session.last_audit_event = event.timestamp
        logger.info("Auth event: %s", line)

    def audit_log(self, limit: int = 200) -> List[AuthEvent]:
        if not self.audit_file.exists():
            return []
        events: List[AuthEvent] = []
        with self.audit_file.open("r", encoding="utf-8") as fh:
            for line in fh.readlines()[-limit:]:
                try:
                    payload = json.loads(line)
                    events.append(AuthEvent(**payload))
                except Exception:
                    continue
        return events

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------
    def refresh_session_state(
        self,
        service: str,
        identity: str,
        *,
        state_path: Path,
        status: str = "ready",
        notes: str = "",
    ) -> AuthSession:
        session = AuthSession(
            service=service,
            identity=identity,
            state_path=str(state_path),
            refreshed_at=time.time(),
            status=status,
            notes=notes,
        )
        key = self._session_key(service, identity)
        with self._lock:
            self._sessions[key] = session
            self._persist_sessions()
            self._log_event(
                AuthEvent(
                    timestamp=session.refreshed_at,
                    service=service,
                    identity=identity,
                    action="session_refreshed",
                    detail=notes,
                )
            )
        return session

    def end_session(self, service: str, identity: str) -> None:
        key = self._session_key(service, identity)
        with self._lock:
            self._sessions.pop(key, None)
            self._persist_sessions()
            self._log_event(
                AuthEvent(
                    timestamp=time.time(),
                    service=service,
                    identity=identity,
                    action="session_ended",
                    detail="Session removed",
                )
            )

    def get_session(self, service: str, identity: str) -> Optional[AuthSession]:
        return self._sessions.get(self._session_key(service, identity))

    # ------------------------------------------------------------------
    # Secrets management
    # ------------------------------------------------------------------
    def store_password(
        self,
        service: str,
        identity: str,
        password: str,
        *,
        metadata: Optional[Dict[str, str]] = None,
        username: Optional[str] = None,
    ) -> None:
        meta = metadata or {}
        self.vault.set_secret(
            f"{service}:{identity}:password",
            password,
            metadata=meta,
        )
        if username:
            self.vault.set_secret(
                f"{service}:{identity}:username",
                username,
                metadata=meta,
            )
        self._log_event(
            AuthEvent(
                timestamp=time.time(),
                service=service,
                identity=identity,
                action="password_updated",
                detail="Password rotated by agent",
            )
        )

    def password_for(self, service: str, identity: str) -> Optional[str]:
        return self.vault.get_secret(f"{service}:{identity}:password")

    def username_for(self, service: str, identity: str) -> Optional[str]:
        return self.vault.get_secret(f"{service}:{identity}:username")

    def list_sessions(self) -> List[AuthSession]:
        return list(self._sessions.values())

    @classmethod
    def default(cls) -> "AuthManager":
        return cls()


__all__ = ["AuthManager", "AuthSession", "AuthEvent", "AUTH_STATE_FILE"]
