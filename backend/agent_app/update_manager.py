"""Self-update orchestration owned by the agent."""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

try:  # pragma: no cover - Python <3.8 fallback
    from importlib import metadata as importlib_metadata
except ImportError:  # pragma: no cover - fallback import
    import importlib_metadata  # type: ignore

try:  # pragma: no cover - optional dependency safety
    import requests
    _REQUESTS_ERROR: Optional[Exception] = None
except Exception as exc:  # pragma: no cover - requests missing
    requests = None  # type: ignore
    _REQUESTS_ERROR = exc

from . import AGENT_STATE_DIR

logger = logging.getLogger(__name__)

STATUS_FILE = AGENT_STATE_DIR / "update_status.json"


_VERSION_TOKEN = re.compile(r"\d+")


def _parse_version(value: str) -> Tuple[int, ...]:
    tokens = _VERSION_TOKEN.findall(value or "0")
    if not tokens:
        return (0,)
    return tuple(int(part) for part in tokens)


@dataclass
class UpdateStatus:
    last_checked: float
    latest_version: str
    installed_version: str
    pending_version: str = ""
    auto_update: bool = True
    download_url: str = ""
    release_notes: str = ""
    previous_version: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "last_checked": self.last_checked,
            "latest_version": self.latest_version,
            "installed_version": self.installed_version,
            "pending_version": self.pending_version,
            "auto_update": self.auto_update,
            "download_url": self.download_url,
            "release_notes": self.release_notes,
            "previous_version": self.previous_version,
        }


class UpdateManager:
    """Check remote feeds and orchestrate update/rollback commands."""

    def __init__(self, state_file: Path = STATUS_FILE) -> None:
        self.state_file = state_file
        self.feed_source = os.getenv("VAMP_UPDATE_FEED", "")
        self.package_name = os.getenv("VAMP_PACKAGE_NAME", "vamp-agent")
        self.update_command = os.getenv("VAMP_UPDATE_COMMAND", "")
        self.rollback_command = os.getenv("VAMP_ROLLBACK_COMMAND", "")

        if not self.state_file.exists():
            self._status = UpdateStatus(time.time(), "0.0.0", "0.0.0")
            self._persist()
        else:
            self._status = self._load()

        self._refresh_installed_version()

    # ------------------------------------------------------------------
    def _persist(self) -> None:
        self.state_file.write_text(json.dumps(self._status.to_dict(), indent=2), encoding="utf-8")

    def _load(self) -> UpdateStatus:
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            return UpdateStatus(
                last_checked=float(data.get("last_checked", time.time())),
                latest_version=str(data.get("latest_version", "0.0.0")),
                installed_version=str(data.get("installed_version", "0.0.0")),
                pending_version=str(data.get("pending_version", "")),
                auto_update=bool(data.get("auto_update", True)),
                download_url=str(data.get("download_url", "")),
                release_notes=str(data.get("release_notes", "")),
                previous_version=str(data.get("previous_version", "")),
            )
        except Exception as exc:  # pragma: no cover - corrupted state files
            logger.warning("Update status file unreadable: %s", exc)
            return UpdateStatus(time.time(), "0.0.0", "0.0.0")

    def _refresh_installed_version(self) -> None:
        detected = self._detect_installed_version()
        if detected and detected != self._status.installed_version:
            self._status.installed_version = detected
            if not self._status.latest_version:
                self._status.latest_version = detected
            self._persist()

    def _detect_installed_version(self) -> str:
        env_version = os.getenv("VAMP_INSTALLED_VERSION")
        if env_version:
            return str(env_version)
        try:
            return importlib_metadata.version(self.package_name)
        except importlib_metadata.PackageNotFoundError:
            return self._status.installed_version or "0.0.0"
        except Exception as exc:  # pragma: no cover - metadata backend failures
            logger.debug("Unable to determine installed version: %s", exc)
            return self._status.installed_version or "0.0.0"

    def _fetch_latest_release(self) -> Optional[Dict[str, str]]:
        source = self.feed_source
        if not source:
            return None

        if source.startswith(("http://", "https://")):
            if requests is None:
                logger.error("requests is required to fetch update feed %s: %s", source, _REQUESTS_ERROR)
                return None
            try:
                response = requests.get(source, timeout=10)
                response.raise_for_status()
                payload = response.json()
            except Exception as exc:  # pragma: no cover - network dependent
                logger.error("Failed to retrieve update feed %s: %s", source, exc)
                return None
        else:
            feed_path = Path(source)
            if not feed_path.exists():
                logger.error("Update feed %s does not exist", source)
                return None
            try:
                payload = json.loads(feed_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.error("Invalid update feed at %s: %s", feed_path, exc)
                return None

        if isinstance(payload, list):
            payload = payload[0] if payload else {}

        if not isinstance(payload, dict):
            logger.error("Unexpected update feed payload: %r", payload)
            return None

        version = str(payload.get("version") or payload.get("tag_name") or "").strip()
        if version.startswith("v"):
            version = version[1:]
        if not version:
            logger.error("Update feed at %s did not include a version", source)
            return None

        release_notes = str(payload.get("release_notes") or payload.get("body") or "").strip()
        download_url = str(
            payload.get("download_url")
            or payload.get("html_url")
            or payload.get("browser_download_url")
            or ""
        )

        return {
            "version": version,
            "release_notes": release_notes,
            "download_url": download_url,
        }

    # ------------------------------------------------------------------
    def status(self) -> Dict[str, object]:
        return self._status.to_dict()

    def check_for_updates(self) -> Dict[str, object]:
        self._status.last_checked = time.time()
        self._refresh_installed_version()

        release = self._fetch_latest_release()
        if not release:
            self._persist()
            return {
                "message": "no_feed",
                "installed": self._status.installed_version,
            }

        latest_version = release["version"]
        self._status.latest_version = latest_version
        self._status.download_url = release.get("download_url", "")
        self._status.release_notes = release.get("release_notes", "")

        if _parse_version(latest_version) > _parse_version(self._status.installed_version):
            self._status.pending_version = latest_version
            self._persist()
            return {
                "message": "update_available",
                "version": latest_version,
                "download_url": self._status.download_url,
                "release_notes": self._status.release_notes,
            }

        self._status.pending_version = ""
        self._persist()
        return {
            "message": "up_to_date",
            "version": self._status.installed_version,
        }

    def _run_command(self, command: str, version: str) -> Optional[Dict[str, object]]:
        if not command:
            return None
        formatted = command.format(version=version)
        try:
            subprocess.check_call(shlex.split(formatted))
        except FileNotFoundError as exc:
            logger.error("Update command not found: %s", exc)
            return {"message": "update_failed", "error": str(exc)}
        except subprocess.CalledProcessError as exc:
            logger.error("Update command failed (%s): %s", formatted, exc)
            return {
                "message": "update_failed",
                "error": str(exc),
                "returncode": exc.returncode,
            }
        return None

    def apply_latest(self) -> Dict[str, object]:
        if not self._status.pending_version:
            return {"message": "no_update"}

        target = self._status.pending_version
        failure = self._run_command(self.update_command, target)
        if failure:
            return failure

        self._status.previous_version = self._status.installed_version
        self._status.installed_version = target
        self._status.pending_version = ""
        self._persist()
        return {"message": "updated", "version": target}

    def rollback(self) -> Dict[str, object]:
        if not self._status.previous_version:
            return {"message": "no_rollback"}

        failure = self._run_command(self.rollback_command, self._status.previous_version)
        if failure:
            return failure

        current = self._status.installed_version
        self._status.installed_version = self._status.previous_version
        self._status.previous_version = ""
        self._status.pending_version = ""
        candidates = [value for value in [self._status.latest_version, current] if value]
        if candidates:
            self._status.latest_version = max(candidates, key=_parse_version)
        self._persist()
        return {"message": "rolled_back", "version": self._status.installed_version}

    @classmethod
    def default(cls) -> "UpdateManager":
        return cls()


__all__ = ["UpdateManager", "UpdateStatus", "STATUS_FILE"]
