"""Encrypted secret storage owned by the agent."""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

try:  # pragma: no cover - optional import
    from cryptography.fernet import Fernet
except Exception:  # pragma: no cover - fallback for environments without cryptography
    Fernet = None  # type: ignore

from . import AGENT_STATE_DIR

logger = logging.getLogger(__name__)

VAULT_FILE = AGENT_STATE_DIR / "secrets.json"
KEY_FILE = AGENT_STATE_DIR / "secrets.key"
ALLOW_INSECURE_VAULT = os.getenv("VAMP_ALLOW_INSECURE_VAULT", "0").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class SecretRecord:
    """Single credential/token entry."""

    name: str
    value: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "value": self.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "SecretRecord":
        return cls(
            name=str(data["name"]),
            value=str(data["value"]),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            metadata=dict(data.get("metadata", {})),
        )


class SecretsVault:
    """Simple encrypted vault that never leaks secrets to the environment."""

    def __init__(self, path: Path = VAULT_FILE, key_path: Path = KEY_FILE) -> None:
        if Fernet is None and not ALLOW_INSECURE_VAULT:
            raise RuntimeError(
                "The 'cryptography' package is required for encrypted secret storage. "
                "Install cryptography to continue or set VAMP_ALLOW_INSECURE_VAULT=1 to permit plaintext storage explicitly."
            )
        if Fernet is None and ALLOW_INSECURE_VAULT:
            logger.warning(
                "cryptography not available; secrets will be stored in plaintext because VAMP_ALLOW_INSECURE_VAULT=1."
            )

        self.path = path
        self.key_path = key_path
        self._fernet: Optional[Fernet] = self._ensure_key()
        self._cache: Dict[str, SecretRecord] = {}
        self._load()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_key(self) -> Optional[Fernet]:
        if Fernet is None:
            return None
        if not self.key_path.exists():
            key = Fernet.generate_key()
            self.key_path.write_bytes(key)
            os.chmod(self.key_path, 0o600)
        else:
            key = self.key_path.read_bytes()
        try:
            return Fernet(key)
        except Exception:
            # Key corrupted - rotate
            new_key = Fernet.generate_key()
            self.key_path.write_bytes(new_key)
            return Fernet(new_key)

    def _load(self) -> None:
        if not self.path.exists():
            self._cache = {}
            return
        raw = self.path.read_text(encoding="utf-8")
        if not raw.strip():
            self._cache = {}
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        secrets_map = payload.get("secrets", {}) if isinstance(payload, dict) else {}
        out: Dict[str, SecretRecord] = {}
        for name, stored in secrets_map.items():
            try:
                record = self._decode_record(name, stored)
            except Exception:
                continue
            out[name] = record
        self._cache = out

    def _decode_record(self, name: str, stored: object) -> SecretRecord:
        if not isinstance(stored, dict):
            raise ValueError("Invalid secret record")
        value = str(stored.get("value", ""))
        if self._fernet is not None and value:
            try:
                decrypted = self._fernet.decrypt(value.encode("utf-8"))
                value = decrypted.decode("utf-8")
            except Exception:
                value = ""
        return SecretRecord(
            name=name,
            value=value,
            created_at=float(stored.get("created_at", time.time())),
            updated_at=float(stored.get("updated_at", time.time())),
            metadata=dict(stored.get("metadata", {})),
        )

    def _encode_record(self, record: SecretRecord) -> Dict[str, object]:
        value = record.value
        if self._fernet is not None and value:
            value = self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")
        return {
            "value": value,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "metadata": record.metadata,
        }

    def _persist(self) -> None:
        payload = {
            "version": 1,
            "secrets": {name: self._encode_record(record) for name, record in self._cache.items()},
        }
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(self.path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list(self) -> Dict[str, SecretRecord]:
        return dict(self._cache)

    def get(self, name: str) -> Optional[SecretRecord]:
        return self._cache.get(name)

    def get_secret(self, name: str) -> Optional[str]:
        record = self.get(name)
        return record.value if record else None

    def set_secret(self, name: str, value: str, *, metadata: Optional[Dict[str, str]] = None) -> SecretRecord:
        record = SecretRecord(
            name=name,
            value=value,
            created_at=time.time(),
            updated_at=time.time(),
            metadata=metadata or {},
        )
        self._cache[name] = record
        self._persist()
        return record

    def delete_secret(self, name: str) -> None:
        if name in self._cache:
            del self._cache[name]
            self._persist()

    def rotate_key(self) -> None:
        if Fernet is None:
            # Provide deterministic pseudo-rotation by shuffling values
            for record in self._cache.values():
                record.value = base64.urlsafe_b64encode(record.value.encode("utf-8")).decode("utf-8")
            self._persist()
            return
        new_key = Fernet.generate_key()
        self.key_path.write_bytes(new_key)
        os.chmod(self.key_path, 0o600)
        self._fernet = Fernet(new_key)
        # Re-encrypt stored values with new key
        current = dict(self._cache)
        self._cache = {}
        for name, record in current.items():
            self._cache[name] = SecretRecord(
                name=name,
                value=record.value,
                created_at=record.created_at,
                updated_at=time.time(),
                metadata=record.metadata,
            )
        self._persist()

    def export_plaintext(self) -> Dict[str, str]:
        """Return all secrets as plaintext for backup/inspection."""
        return {name: record.value for name, record in self._cache.items()}

    @classmethod
    def default(cls) -> "SecretsVault":
        return cls()


__all__ = ["SecretsVault", "SecretRecord", "VAULT_FILE", "KEY_FILE"]
