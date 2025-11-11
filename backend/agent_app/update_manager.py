"""Self-update orchestration owned by the agent."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from . import AGENT_STATE_DIR

STATUS_FILE = AGENT_STATE_DIR / "update_status.json"


@dataclass
class UpdateStatus:
    last_checked: float
    latest_version: str
    installed_version: str
    pending_version: str = ""
    auto_update: bool = True

    def to_dict(self) -> Dict[str, object]:
        return {
            "last_checked": self.last_checked,
            "latest_version": self.latest_version,
            "installed_version": self.installed_version,
            "pending_version": self.pending_version,
            "auto_update": self.auto_update,
        }


class UpdateManager:
    """Currently a stub that simulates update workflows."""

    def __init__(self, state_file: Path = STATUS_FILE) -> None:
        self.state_file = state_file
        if not self.state_file.exists():
            self._status = UpdateStatus(time.time(), "0.0.0", "0.0.0")
            self._persist()
        else:
            self._status = self._load()

    def _persist(self) -> None:
        import json

        self.state_file.write_text(json.dumps(self._status.to_dict(), indent=2), encoding="utf-8")

    def _load(self) -> UpdateStatus:
        import json

        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            return UpdateStatus(
                last_checked=float(data.get("last_checked", time.time())),
                latest_version=str(data.get("latest_version", "0.0.0")),
                installed_version=str(data.get("installed_version", "0.0.0")),
                pending_version=str(data.get("pending_version", "")),
                auto_update=bool(data.get("auto_update", True)),
            )
        except Exception:
            return UpdateStatus(time.time(), "0.0.0", "0.0.0")

    # ------------------------------------------------------------------
    def status(self) -> Dict[str, object]:
        return self._status.to_dict()

    def check_for_updates(self) -> Dict[str, object]:
        self._status.last_checked = time.time()
        major, minor, patch = (int(x) for x in self._status.installed_version.split("."))
        patch += 1
        suggested = f"{major}.{minor}.{patch}"
        self._status.latest_version = suggested
        self._status.pending_version = suggested
        self._persist()
        return {"message": "update_available", "version": suggested}

    def apply_latest(self) -> Dict[str, object]:
        if not self._status.pending_version:
            return {"message": "no_update"}
        self._status.installed_version = self._status.pending_version
        self._status.pending_version = ""
        self._persist()
        return {"message": "updated", "version": self._status.installed_version}

    def rollback(self) -> Dict[str, object]:
        if not self._status.pending_version:
            return {"message": "no_rollback"}
        self._status.pending_version = ""
        self._persist()
        return {"message": "rollback_cleared"}

    @classmethod
    def default(cls) -> "UpdateManager":
        return cls()


__all__ = ["UpdateManager", "UpdateStatus", "STATUS_FILE"]
