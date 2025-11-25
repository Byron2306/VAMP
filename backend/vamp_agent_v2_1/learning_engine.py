from __future__ import annotations

"""Self-learning utilities for the autonomous agent.

The LearningEngine ingests corrections and reflective feedback to adjust
keyword importance weights and calibration parameters. It operates purely in
memory for now and records a lightweight history that can be surfaced for
telemetry or debugging.
"""

import datetime as _dt
from collections import deque
from typing import Deque, Dict, List, Mapping, MutableMapping, Optional

from .audit_logger import AuditLogger


class LearningEngine:
    """Update keyword and calibration weights based on feedback signals."""

    def __init__(
        self,
        keyword_importance: MutableMapping[str, float],
        calibration: MutableMapping[str, float],
        audit_logger: Optional[AuditLogger] = None,
        learning_rate: float = 0.05,
    ) -> None:
        self.keyword_importance = keyword_importance
        self.calibration = calibration
        self.audit_logger = audit_logger
        self.learning_rate = learning_rate
        self.history: Deque[Dict[str, object]] = deque()

    def ingest_director_correction(
        self, evidence: Mapping[str, object], predicted_kpa: str, corrected_kpa: str
    ) -> None:
        """Apply updates when a director overrides a predicted KPA."""

        evidence_id = self._extract_evidence_id(evidence)
        tokens = self._tokenize(self._extract_text(evidence))

        delta_summary: Dict[str, float] = {}

        for token in tokens:
            delta = self._apply_weight_update(token, self.learning_rate)
            delta_summary[token] = delta_summary.get(token, 0.0) + delta

        if predicted_kpa and corrected_kpa and predicted_kpa != corrected_kpa:
            penalty = -self.learning_rate * 0.5
            for token in tokens:
                delta = self._apply_weight_update(token, penalty)
                delta_summary[token] = delta_summary.get(token, 0.0) + delta

        self._record_history(
            evidence_id,
            "director_correction",
            delta_summary,
            metadata={"predicted": predicted_kpa, "corrected": corrected_kpa},
        )
        self._log_learning_signal(evidence_id, delta_summary, "director_correction")

    def ingest_reflection_feedback(self, evidence: Mapping[str, object], tags_or_notes: object) -> None:
        """Ingest lower-signal reflective feedback from the agent itself."""

        evidence_id = self._extract_evidence_id(evidence)
        tokens = self._tokenize(self._extract_text(evidence))
        feedback_tokens = self._tokenize(str(tags_or_notes))

        delta_summary: Dict[str, float] = {}
        mild_rate = self.learning_rate * 0.2

        for token in tokens + feedback_tokens:
            delta = self._apply_weight_update(token, mild_rate)
            delta_summary[token] = delta_summary.get(token, 0.0) + delta

        if feedback_tokens:
            self.calibration["reflection_bias"] = self.calibration.get("reflection_bias", 0.0) + mild_rate

        self._record_history(evidence_id, "reflection", delta_summary, metadata={"notes": tags_or_notes})
        self._log_learning_signal(evidence_id, delta_summary, "reflection")

    def get_learning_history(self, limit: int = 100) -> List[Dict[str, object]]:
        return list(self.history)[-limit:]

    def _apply_weight_update(self, token: str, delta: float) -> float:
        token_key = token.lower()
        previous = float(self.keyword_importance.get(token_key, 0.0))
        updated = previous + delta
        self.keyword_importance[token_key] = updated
        return updated - previous

    def _record_history(
        self,
        evidence_id: str,
        event_type: str,
        delta_summary: Mapping[str, float],
        metadata: Optional[Mapping[str, object]] = None,
    ) -> None:
        entry = {
            "timestamp": _dt.datetime.utcnow().isoformat(),
            "evidence_id": evidence_id,
            "event": event_type,
            "delta": dict(delta_summary),
            "metadata": dict(metadata) if metadata else {},
        }
        self.history.append(entry)
        while len(self.history) > 500:
            self.history.popleft()

    def _log_learning_signal(self, evidence_id: str, delta_summary: Mapping[str, float], event_type: str) -> None:
        if not self.audit_logger:
            return
        self.audit_logger.log(
            "LEARNING_SIGNAL",
            {
                "evidence_id": evidence_id,
                "event_type": event_type,
                "delta": dict(delta_summary),
            },
        )

    def _extract_text(self, evidence: Mapping[str, object]) -> str:
        for key in ("text", "content", "body"):
            if key in evidence and evidence[key] is not None:
                return str(evidence[key])
        return ""

    def _extract_evidence_id(self, evidence: Mapping[str, object]) -> str:
        for key in ("evidence_id", "id", "uid"):
            if key in evidence:
                return str(evidence[key])
        return "unknown"

    def _tokenize(self, text: str) -> List[str]:
        if not text:
            return []
        return [token.lower() for token in text.replace("\n", " ").split() if token]
