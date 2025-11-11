"""Agent-owned authentication orchestration."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

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
    """Represents an authentication session managed by the agent."""

    service: str
    identity: str
    access_token: str = ""
    refresh_token: str = ""
    expires_at: Optional[float] = None
    scopes: List[str] = field(default_factory=list)
    last_audit_event: Optional[float] = None

    def is_expired(self) -> bool:
        return self.expires_at is not None and time.time() >= self.expires_at

    def to_dict(self) -> Dict[str, object]:
        return {
            "service": self.service,
            "identity": self.identity,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "scopes": self.scopes,
            "last_audit_event": self.last_audit_event,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "AuthSession":
        return cls(
            service=str(data["service"]),
            identity=str(data.get("identity", "")),
            access_token=str(data.get("access_token", "")),
            refresh_token=str(data.get("refresh_token", "")),
            expires_at=data.get("expires_at"),
            scopes=list(data.get("scopes", [])),
            last_audit_event=data.get("last_audit_event"),
        )


class AuthManager:
    """Central orchestrator for authentication flows."""

    def __init__(self, vault: Optional[SecretsVault] = None, audit_file: Path = AGENT_LOG_DIR / "auth.log") -> None:
        self.vault = vault or SecretsVault.default()
        self.audit_file = audit_file
        self._sessions: Dict[str, AuthSession] = {}
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
    def start_session(
        self,
        service: str,
        identity: str,
        *,
        access_token: str,
        refresh_token: str = "",
        expires_in: Optional[int] = None,
        scopes: Optional[Iterable[str]] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> AuthSession:
        expires_at = time.time() + int(expires_in) if expires_in else None
        session = AuthSession(
            service=service,
            identity=identity,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scopes=list(scopes or []),
        )
        key = self._session_key(service, identity)
        self._sessions[key] = session
        self.vault.set_secret(
            f"{service}:{identity}:access_token",
            access_token,
            metadata=metadata or {},
        )
        if refresh_token:
            self.vault.set_secret(
                f"{service}:{identity}:refresh_token",
                refresh_token,
                metadata=metadata or {},
            )
        self._persist_sessions()
        self._log_event(
            AuthEvent(
                timestamp=time.time(),
                service=service,
                identity=identity,
                action="session_started",
                detail="Agent captured OAuth tokens",
            )
        )
        return session

    def end_session(self, service: str, identity: str) -> None:
        key = self._session_key(service, identity)
        if key in self._sessions:
            del self._sessions[key]
            self._persist_sessions()
        self.vault.delete_secret(f"{service}:{identity}:access_token")
        self.vault.delete_secret(f"{service}:{identity}:refresh_token")
        self._log_event(
            AuthEvent(
                timestamp=time.time(),
                service=service,
                identity=identity,
                action="session_ended",
                detail="Tokens removed per user request",
            )
        )

    def get_session(self, service: str, identity: str) -> Optional[AuthSession]:
        return self._sessions.get(self._session_key(service, identity))

    def get_credentials(self, service: str, identity: str = "") -> Dict[str, Optional[str]]:
        """Return sanitized credential bundle for automation."""
        key_prefix = f"{service}:{identity or 'default'}"
        access = self.vault.get_secret(f"{key_prefix}:access_token")
        refresh = self.vault.get_secret(f"{key_prefix}:refresh_token")
        session = self._sessions.get(self._session_key(service, identity))
        if session and session.is_expired():
            self._log_event(
                AuthEvent(
                    timestamp=time.time(),
                    service=service,
                    identity=identity,
                    action="token_expired",
                    detail="Access token expired; refresh required",
                )
            )
        return {
            "access_token": access,
            "refresh_token": refresh,
            "expires_at": session.expires_at if session else None,
            "scopes": session.scopes if session else [],
        }

    def store_password(self, service: str, identity: str, password: str, *, metadata: Optional[Dict[str, str]] = None) -> None:
        meta = metadata or {}
        self.vault.set_secret(
            f"{service}:{identity}:password",
            password,
            metadata=meta,
        )
        username = meta.get("username")
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
        secret = self.vault.get_secret(f"{service}:{identity}:username")
        if secret:
            return secret
        return None

    def list_sessions(self) -> List[AuthSession]:
        return list(self._sessions.values())

    @classmethod
    def default(cls) -> "AuthManager":
        return cls()


__all__ = ["AuthManager", "AuthSession", "AuthEvent", "AUTH_STATE_FILE"]
