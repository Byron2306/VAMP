"""Fire-and-forget bridge into the offline AutonomousAgentService.

This module keeps the AutonomousAgentService configured with the NWU brain
assets and exposes small helper functions that can be called from existing
ingestion paths without disrupting CSV exports or vault writes. Calls are
best-effort and silently ignored if the agent is disabled or initialisation
fails.
"""
from __future__ import annotations

import logging
import shutil
import threading
import uuid
from pathlib import Path
from typing import Mapping, MutableMapping, Optional

from . import DATA_DIR
from .settings import VAMP_AGENT_ENABLED
from .vamp_agent_v2_1.autonomous_agent_service import AutonomousAgentService

logger = logging.getLogger(__name__)

BRIDGE_ROOT = DATA_DIR / "autonomous_agent"
KPA_BASE_DIR = BRIDGE_ROOT / "kpa"
DIRECTOR_QUEUE_DIR = BRIDGE_ROOT / "director_queue"
DUMP_DIR = BRIDGE_ROOT / "dumps"
SPOOL_DIR = BRIDGE_ROOT / "ingest_queue"

_LOCK = threading.Lock()
_SERVICE: Optional[AutonomousAgentService] = None
_WORKER: Optional[threading.Thread] = None


def _ensure_directories() -> None:
    for path in (KPA_BASE_DIR, DIRECTOR_QUEUE_DIR, DUMP_DIR, SPOOL_DIR):
        path.mkdir(parents=True, exist_ok=True)


def _start_service() -> Optional[AutonomousAgentService]:
    global _SERVICE
    if not VAMP_AGENT_ENABLED:
        return None

    with _LOCK:
        if _SERVICE is not None:
            return _SERVICE

        try:
            _ensure_directories()
            _SERVICE = AutonomousAgentService(
                kpa_base_path=KPA_BASE_DIR,
                director_queue_path=DIRECTOR_QUEUE_DIR,
                dump_dir=DUMP_DIR,
            )
            _start_worker(_SERVICE)
        except Exception:  # pragma: no cover - resilience path
            logger.debug("Failed to start AutonomousAgentService", exc_info=True)
            _SERVICE = None
    return _SERVICE


def _start_worker(service: AutonomousAgentService) -> None:
    global _WORKER
    if _WORKER and _WORKER.is_alive():
        return

    def _loop() -> None:
        try:
            service.run_forever()
        except Exception:  # pragma: no cover - background resilience path
            logger.debug("Autonomous agent loop stopped", exc_info=True)

    _WORKER = threading.Thread(target=_loop, name="autonomous-agent", daemon=True)
    _WORKER.start()


def _clone_path(src: Path) -> Optional[Path]:
    if not src.exists():
        return None
    try:
        SPOOL_DIR.mkdir(parents=True, exist_ok=True)
        dest = SPOOL_DIR / f"{src.stem}_{uuid.uuid4().hex}{src.suffix}"
        shutil.copy2(src, dest)
        return dest
    except Exception:  # pragma: no cover - best effort clone
        logger.debug("Failed to clone evidence for agent bridge", exc_info=True)
        return None


def _normalize_payload(raw: Mapping[str, object]) -> MutableMapping[str, object]:
    payload: MutableMapping[str, object] = dict(raw)

    path_value = raw.get("path") or raw.get("file_path") or raw.get("filepath")
    cloned_path: Optional[Path] = None
    if path_value:
        try:
            cloned_path = _clone_path(Path(str(path_value)))
        except Exception:  # pragma: no cover - guard for malformed paths
            logger.debug("Invalid evidence path provided to agent bridge", exc_info=True)
            cloned_path = None

    if cloned_path:
        payload["path"] = cloned_path
    else:
        payload.pop("path", None)
        payload.pop("file_path", None)
        payload.pop("filepath", None)

    evidence_id = payload.get("evidence_id") or payload.get("uid") or payload.get("hash")
    if evidence_id:
        payload["evidence_id"] = str(evidence_id)
    else:
        guessed_name = cloned_path.name if cloned_path else None
        payload["evidence_id"] = guessed_name or uuid.uuid4().hex

    if "modality" not in payload:
        payload["modality"] = "text"

    return payload


def submit_evidence_from_vamp(evidence: Mapping[str, object]) -> None:
    """Queue evidence for the autonomous agent without altering callers."""

    if not VAMP_AGENT_ENABLED:
        return
    service = _start_service()
    if not service:
        return

    try:
        normalized = _normalize_payload(evidence)
        service.enqueue_evidence(normalized)
    except Exception:  # pragma: no cover - never break ingestion flows
        logger.debug("Failed to enqueue evidence for autonomous agent", exc_info=True)


def submit_director_feedback(feedback: Mapping[str, object]) -> None:
    """Queue director feedback for the autonomous agent if available."""

    if not VAMP_AGENT_ENABLED:
        return
    service = _start_service()
    if not service:
        return

    try:
        service.enqueue_feedback(dict(feedback))
    except Exception:  # pragma: no cover - resilience path
        logger.debug("Failed to enqueue director feedback", exc_info=True)


__all__ = [
    "submit_evidence_from_vamp",
    "submit_director_feedback",
]
