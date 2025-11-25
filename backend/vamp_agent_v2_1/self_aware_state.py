"""State tracking utilities for Autonomous Agent v2.1.

SelfAwareState tracks processing metrics, error counts, and learning statistics
so the agent can report health and adjust behaviour without impacting existing
VAMP workflows. Logic is intentionally minimal for initial scaffolding.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Mapping, Optional

from .audit_logger import AuditLogger


@dataclass
class SelfAwareState:
    """Container for runtime metrics and operational counters."""

    audit_logger: Optional[AuditLogger] = None
    evidence_processed_count: int = 0
    processed_items: int = 0
    error_count: int = 0
    approvals: int = 0
    corrections: int = 0
    pending_reviews: int = 0
    director_queue_depth: int = 0
    rolling_window: int = 50
    custom_metrics: Dict[str, int] = field(default_factory=dict)
    errors_by_type: Dict[str, int] = field(default_factory=dict)
    _rolling_outcomes: Deque[bool] = field(init=False, repr=False)
    _last_logged_snapshot: Dict[str, object] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self._rolling_outcomes = deque(maxlen=self.rolling_window)

    def increment(self, metric: str, amount: int = 1) -> None:
        """Increment a numeric metric by a given amount.

        Unknown metrics are tracked inside ``custom_metrics`` to avoid raising
        exceptions and to preserve compatibility with future additions.
        """

        if hasattr(self, metric):
            current_value = getattr(self, metric)
            setattr(self, metric, current_value + amount)
        else:
            self.custom_metrics[metric] = self.custom_metrics.get(metric, 0) + amount
        self._log_snapshot_if_needed()

    def update_after_classification(self, result: Mapping[str, object], approved: Optional[bool]) -> None:
        """Update counters following a classification event.

        Parameters
        ----------
        result: Mapping[str, object]
            Classification result dictionary. Currently used only for telemetry.
        approved: Optional[bool]
            Whether the classification was confirmed (True), corrected (False),
            or left unreviewed (None).
        """

        self.evidence_processed_count += 1
        self.processed_items = self.evidence_processed_count
        if approved is True:
            self.approvals += 1
            self._rolling_outcomes.append(True)
        elif approved is False:
            self.corrections += 1
            self._rolling_outcomes.append(False)
        else:
            self.pending_reviews += 1
        self._log_snapshot_if_needed()

    def update_after_error(self, error_type: str) -> None:
        """Register an operational error and track it by category."""

        self.error_count += 1
        self.errors_by_type[error_type] = self.errors_by_type.get(error_type, 0) + 1
        self._log_snapshot_if_needed()

    def snapshot(self) -> Dict[str, object]:
        """Return a shallow copy of the current metrics."""

        return self.to_dict()

    def to_dict(self) -> Dict[str, object]:
        evaluated = self.approvals + self.corrections
        accuracy_estimate = None if evaluated == 0 else self.approvals / evaluated
        rolling_accuracy = None
        if self._rolling_outcomes:
            rolling_accuracy = sum(self._rolling_outcomes) / len(self._rolling_outcomes)

        return {
            "evidence_processed_count": self.evidence_processed_count,
            "processed_items": self.processed_items,
            "error_count": self.error_count,
            "approvals": self.approvals,
            "corrections": self.corrections,
            "pending_reviews": self.pending_reviews,
            "accuracy_estimate": accuracy_estimate,
            "rolling_accuracy": rolling_accuracy,
            "director_queue_depth": self.director_queue_depth,
            "custom_metrics": dict(self.custom_metrics),
            "errors_by_type": dict(self.errors_by_type),
        }

    def _log_snapshot_if_needed(self) -> None:
        snapshot = self.to_dict()
        if snapshot == self._last_logged_snapshot:
            return
        self._last_logged_snapshot = snapshot
        if self.audit_logger:
            self.audit_logger.log("STATE_SNAPSHOT", snapshot)
