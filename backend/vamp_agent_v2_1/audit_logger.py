"""Append-only audit logging for Autonomous Agent v2.1.

The AuditLogger ensures all operations are recorded immutably for traceability
and compliance. Business logic is intentionally minimal at this stage; future
iterations will implement log rotation, hashing, and persistence rules.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional


class AuditLogger:
    """Append-only logger that writes structured audit entries to disk.

    This class is designed to be extended with hashing, integrity checks, and
    tamper-evident storage. For now, it records messages to a log file when
    enabled, ensuring existing VAMP behaviour remains unchanged.
    """

    def __init__(self, log_path: Path, enabled: bool = True) -> None:
        self.log_path = Path(log_path)
        self.enabled = enabled
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, message: str, context: Optional[dict] = None) -> None:
        """Append a single log entry.

        Parameters
        ----------
        message: str
            Human-readable log message.
        context: Optional[dict]
            Additional structured metadata to include with the entry.
        """

        if not self.enabled:
            return

        entry = self._format_entry(message, context)
        with self.log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(entry)

    def log_many(self, messages: Iterable[str]) -> None:
        """Append multiple log entries in a batch.

        This method currently writes entries sequentially; future iterations may
        implement buffered writes with durability guarantees.
        """

        for message in messages:
            self.log(message)

    def log_classification(self, evidence_id: str, result: dict) -> None:
        """Persist a structured classification result."""

        if not self.enabled:
            return

        entry = {"type": "classification", "evidence_id": evidence_id, "result": result}
        self._append_json(entry)

    def log_routing(self, evidence_id: str, destination: str, reason: Optional[str] = None) -> None:
        """Persist routing actions with optional reason metadata."""

        if not self.enabled:
            return

        entry = {
            "type": "routing",
            "evidence_id": evidence_id,
            "destination": destination,
            "reason": reason,
        }
        self._append_json(entry)

    def _append_json(self, payload: dict) -> None:
        with self.log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(payload) + "\n")

    def _format_entry(self, message: str, context: Optional[dict] = None) -> str:
        """Return a formatted log line for persistence.

        TODO: add timestamps, hashes, and strict schema validation once core
        behaviour is defined.
        """

        suffix = f" | context={context}" if context else ""
        return f"{message}{suffix}\n"
