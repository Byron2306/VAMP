"""State tracking utilities for Autonomous Agent v2.1.

SelfAwareState tracks processing metrics, error counts, and learning statistics
so the agent can report health and adjust behaviour without impacting existing
VAMP workflows. Logic is intentionally minimal for initial scaffolding.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class SelfAwareState:
    """Container for runtime metrics and operational counters."""

    processed_items: int = 0
    routing_errors: int = 0
    classification_errors: int = 0
    learning_updates: int = 0
    director_queue_depth: int = 0
    custom_metrics: Dict[str, int] = field(default_factory=dict)

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

    def snapshot(self) -> Dict[str, int]:
        """Return a shallow copy of the current metrics."""

        return {
            "processed_items": self.processed_items,
            "routing_errors": self.routing_errors,
            "classification_errors": self.classification_errors,
            "learning_updates": self.learning_updates,
            "director_queue_depth": self.director_queue_depth,
            "custom_metrics": dict(self.custom_metrics),
        }
