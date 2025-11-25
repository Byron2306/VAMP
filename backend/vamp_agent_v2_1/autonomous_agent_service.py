"""Autonomous agent orchestration loop (offline, stage 4).

This module wires together the deterministic subsystems introduced in previous
stages. The agent processes an in-memory queue of evidence objects, normalizes
inputs, classifies, routes, learns from feedback, and periodically persists
state snapshots. No external services are contacted at this stage.
"""
from __future__ import annotations

import time
from collections import deque
from pathlib import Path
from typing import Deque, Dict, Iterable, Mapping, MutableMapping, Optional

from .audit_logger import AuditLogger
from .background_scheduler import BackgroundScheduler
from .config_loader import _load_json, load_device_profiles, load_kpa_config, load_policy_rules
from .evidence_classifier import EvidenceClassifier
from .evidence_router import EvidenceRouter
from .learning_engine import LearningEngine
from .memory_dumper import MemoryDumper
from .performance_monitor import PerformanceMonitor
from .self_aware_state import SelfAwareState


class MultimodalProcessor:
    """Basic multimodal normalizer used prior to classification."""

    def normalize(self, evidence: Mapping[str, object]) -> Dict[str, object]:
        normalized = dict(evidence)

        path_value = evidence.get("path") or evidence.get("file_path") or evidence.get("filepath")
        normalized_path = Path(path_value) if path_value else None

        if normalized_path and not normalized_path.exists():
            raise FileNotFoundError(f"Evidence path does not exist: {normalized_path}")

        evidence_id = (
            evidence.get("evidence_id")
            or evidence.get("id")
            or evidence.get("uid")
            or (normalized_path.stem if normalized_path else "unknown")
        )

        text_fields: Iterable[str] = (
            str(evidence.get("text") or ""),
            str(evidence.get("content") or ""),
            str(evidence.get("body") or ""),
        )
        text = next((field for field in text_fields if field), "")

        if not text and normalized_path and normalized_path.is_file():
            try:
                text = normalized_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:  # noqa: BLE001
                text = ""

        normalized.update(
            {
                "evidence_id": str(evidence_id),
                "text": text,
                "path": normalized_path,
                "modality": evidence.get("modality") or "text",
                "received_ts": evidence.get("received_ts") or time.time(),
            }
        )
        return normalized


class AutonomousAgentService:
    """Offline orchestration service for the Autonomous Agent."""

    def __init__(
        self,
        kpa_base_path: Path,
        director_queue_path: Path,
        dump_dir: Path,
        *,
        kpa_config_path: Optional[Path] = None,
        policy_rules_path: Optional[Path] = None,
        device_profiles_path: Optional[Path] = None,
        audit_log_path: Optional[Path] = None,
        device_profile: str = "workstation",
        base_batch_size: int = 5,
        dump_every_n: int = 25,
        dump_every_seconds: int = 300,
    ) -> None:
        self.kpa_config = self._load_config(kpa_config_path, load_kpa_config)
        self.policy_rules = self._load_config(policy_rules_path, load_policy_rules)
        device_profiles = self._load_config(device_profiles_path, load_device_profiles)
        self.device_profile = device_profiles.get(device_profile, {})

        self.audit_logger = AuditLogger(audit_log_path or Path(dump_dir) / "audit.log")
        self.performance_monitor = PerformanceMonitor()
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()

        self.keyword_importance: MutableMapping[str, float] = {}
        self.calibration: MutableMapping[str, float] = {"global": 1.0}

        self.classifier = EvidenceClassifier(
            self.kpa_config,
            keyword_importance=self.keyword_importance,
            calibration=self.calibration.get("global", 1.0),
        )
        self.router = EvidenceRouter(Path(kpa_base_path), Path(director_queue_path), self.policy_rules)
        self.learning_engine = LearningEngine(
            self.keyword_importance, self.calibration, audit_logger=self.audit_logger
        )
        self.state = SelfAwareState(audit_logger=self.audit_logger)
        self.memory_dumper = MemoryDumper(Path(dump_dir))
        self.processor = MultimodalProcessor()

        self.evidence_queue: Deque[Mapping[str, object]] = deque()
        self.feedback_queue: Deque[Mapping[str, object]] = deque()

        self.base_batch_size = base_batch_size
        self.dump_every_n = max(1, dump_every_n)
        self.dump_every_seconds = max(1, dump_every_seconds)
        self.last_dump_time = time.time()
        self.processed_since_dump = 0
        self.running = False

    def enqueue_evidence(self, evidence: Mapping[str, object]) -> None:
        """Push normalized evidence onto the in-memory queue."""

        self.evidence_queue.append(dict(evidence))
        self.audit_logger.log("RECEIVED", {"evidence_id": evidence.get("evidence_id")})

    def enqueue_feedback(self, feedback: Mapping[str, object]) -> None:
        """Push director feedback for later learning."""

        self.feedback_queue.append(dict(feedback))
        self.audit_logger.log("FEEDBACK_ENQUEUED", feedback)

    def run_once(self) -> int:
        """Process a single batch of evidence and feedback."""

        self._process_feedback_queue(limit=self.base_batch_size)

        batch_size = self._determine_batch_size()
        processed = 0

        while processed < batch_size and self.evidence_queue:
            evidence = self.evidence_queue.popleft()
            try:
                normalized = self.processor.normalize(evidence)
                evidence_id = normalized.get("evidence_id", "unknown")
                self.audit_logger.log("NORMALIZED", {"evidence_id": evidence_id})

                self._refresh_classifier_calibration()
                classification = self.classifier.classify(normalized)
                self.audit_logger.log_classification(evidence_id, classification)

                routing = self.router.route(normalized, classification)
                self.audit_logger.log_routing(evidence_id, str(routing.get("destination")), routing.get("reason"))

                self.state.update_after_classification(classification, approved=None)
                self.processed_since_dump += 1
                processed += 1
                self._maybe_dump_memory()
            except Exception as exc:  # noqa: BLE001
                self.state.update_after_error(type(exc).__name__)
                self.audit_logger.log("ERROR", {"error": str(exc), "evidence": evidence})
        return processed

    def run_forever(self, sleep_interval: float = 0.1) -> None:
        """Continuously process the evidence queue until stopped."""

        self.running = True
        try:
            while self.running:
                processed = self.run_once()
                interval = self._determine_sleep_interval(sleep_interval, processed)
                time.sleep(interval)
        finally:
            self.graceful_shutdown()

    def graceful_shutdown(self) -> None:
        """Flush background work and stop auxiliary components."""

        self.running = False
        self.scheduler.stop()

    def _process_feedback_queue(self, limit: int) -> None:
        count = 0
        while self.feedback_queue and count < limit:
            feedback = self.feedback_queue.popleft()
            evidence = feedback.get("evidence", {}) if isinstance(feedback, Mapping) else {}
            predicted = feedback.get("predicted_kpa") if isinstance(feedback, Mapping) else None
            corrected = feedback.get("corrected_kpa") if isinstance(feedback, Mapping) else None
            notes = feedback.get("notes") if isinstance(feedback, Mapping) else None

            if corrected:
                self.learning_engine.ingest_director_correction(
                    evidence, predicted_kpa=predicted, corrected_kpa=corrected
                )
                self.state.increment("corrections", 1)
                self.audit_logger.log("FEEDBACK_APPLIED", feedback)
            elif notes is not None:
                self.learning_engine.ingest_reflection_feedback(evidence, notes)
                self.audit_logger.log("REFLECTION_APPLIED", feedback)

            self._refresh_classifier_calibration()
            count += 1

    def _determine_batch_size(self) -> int:
        metrics = self.performance_monitor.snapshot()
        cpu = float(metrics.get("cpu_percent", 0.0))
        mem = float(metrics.get("memory_percent", 0.0))

        profile_batch = int(self.device_profile.get("batch_size", self.base_batch_size))
        batch_size = max(1, profile_batch)

        if cpu > float(self.device_profile.get("max_cpu_percent", 100)):
            batch_size = max(1, batch_size // 2)
        if mem > float(self.device_profile.get("max_memory_percent", 100)):
            batch_size = max(1, batch_size // 2)

        if cpu > 90 or mem > 90:
            batch_size = 1
        return batch_size

    def _determine_sleep_interval(self, base_interval: float, processed: int) -> float:
        if processed == 0:
            return min(base_interval * 2, 1.0)
        metrics = self.performance_monitor.snapshot()
        cpu = float(metrics.get("cpu_percent", 0.0))
        mem = float(metrics.get("memory_percent", 0.0))
        if cpu < 30 and mem < 30:
            return max(0.01, base_interval * 0.5)
        if cpu > 80 or mem > 80:
            return min(1.0, base_interval * 2)
        return base_interval

    def _maybe_dump_memory(self) -> None:
        now = time.time()
        if self.processed_since_dump < self.dump_every_n and (now - self.last_dump_time) < self.dump_every_seconds:
            return

        label = f"state_dump_{int(now)}"
        state_snapshot = {
            "state": self.state.to_dict(),
            "keyword_importance": dict(self.keyword_importance),
            "calibration": dict(self.calibration),
        }
        if not self.scheduler.schedule(lambda: self.memory_dumper.create_dump(state_snapshot, label)):
            self.memory_dumper.create_dump(state_snapshot, label)
        self.last_dump_time = now
        self.processed_since_dump = 0

    def _refresh_classifier_calibration(self) -> None:
        self.classifier.calibration_factor = float(self.calibration.get("global", 1.0))

    @staticmethod
    def _load_config(path: Optional[Path], fallback_loader) -> Dict[str, object]:
        if path:
            return _load_json(Path(path))
        return fallback_loader()

    def flush_background_tasks(self, timeout: float = 1.0) -> None:
        """Best-effort wait for scheduled tasks to drain (testing helper)."""

        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.scheduler.queue.empty():
                break
            time.sleep(0.05)
