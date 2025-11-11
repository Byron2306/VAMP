"""Agent-controlled evidence vault with chain-of-custody auditing."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from . import AGENT_LOG_DIR, AGENT_STATE_DIR

logger = logging.getLogger(__name__)

EVIDENCE_FILE = AGENT_STATE_DIR / "evidence_store.json"
EVIDENCE_LOG = AGENT_LOG_DIR / "evidence.log"


@dataclass
class EvidenceRecord:
    uid: str
    source: str
    title: str
    kpas: List[int]
    score: float
    rationale: str
    created_at: float = field(default_factory=time.time)
    retention_days: int = 365
    metadata: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "uid": self.uid,
            "source": self.source,
            "title": self.title,
            "kpas": self.kpas,
            "score": self.score,
            "rationale": self.rationale,
            "created_at": self.created_at,
            "retention_days": self.retention_days,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "EvidenceRecord":
        return cls(
            uid=str(data["uid"]),
            source=str(data.get("source", "")),
            title=str(data.get("title", "")),
            kpas=list(data.get("kpas", [])),
            score=float(data.get("score", 0.0)),
            rationale=str(data.get("rationale", "")),
            created_at=float(data.get("created_at", time.time())),
            retention_days=int(data.get("retention_days", 365)),
            metadata=dict(data.get("metadata", {})),
        )


class EvidenceVault:
    def __init__(self, store_file: Path = EVIDENCE_FILE, log_file: Path = EVIDENCE_LOG) -> None:
        self.store_file = store_file
        self.log_file = log_file
        self._records: Dict[str, EvidenceRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.store_file.exists():
            return
        try:
            data = json.loads(self.store_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load evidence store: %s", exc)
            data = {"records": []}
        records = data.get("records", []) if isinstance(data, dict) else []
        for raw in records:
            try:
                record = EvidenceRecord.from_dict(raw)
            except Exception:
                continue
            self._records[record.uid] = record

    def _persist(self) -> None:
        payload = {"records": [record.to_dict() for record in self._records.values()]}
        self.store_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _log(self, action: str, uid: str, detail: str = "") -> None:
        entry = {
            "timestamp": time.time(),
            "action": action,
            "uid": uid,
            "detail": detail,
        }
        with self.log_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    # ------------------------------------------------------------------
    def record(self, record: EvidenceRecord) -> None:
        self._records[record.uid] = record
        self._persist()
        self._log("recorded", record.uid, f"source={record.source}")

    def delete(self, uid: str, reason: str = "user_request") -> None:
        if uid in self._records:
            del self._records[uid]
            self._persist()
        self._log("deleted", uid, reason)

    def list(self) -> List[EvidenceRecord]:
        return sorted(self._records.values(), key=lambda record: record.created_at, reverse=True)

    def export(self) -> Dict[str, object]:
        return {"records": [record.to_dict() for record in self.list()]}

    def retention_summary(self) -> Dict[str, object]:
        now = time.time()
        soon = [record.uid for record in self._records.values() if now - record.created_at > record.retention_days * 86400]
        return {
            "total": len(self._records),
            "pending_deletion": soon,
        }

    @classmethod
    def default(cls) -> "EvidenceVault":
        return cls()


__all__ = ["EvidenceVault", "EvidenceRecord", "EVIDENCE_FILE", "EVIDENCE_LOG"]
