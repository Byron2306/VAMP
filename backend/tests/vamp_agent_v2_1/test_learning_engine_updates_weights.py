from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.vamp_agent_v2_1.audit_logger import AuditLogger
from backend.vamp_agent_v2_1.learning_engine import LearningEngine


def test_learning_engine_applies_director_corrections(tmp_path):
    keyword_importance = {"alpha": 0.1, "beta": 0.0}
    calibration = {"KPA_1": 1.0}
    logger = AuditLogger(tmp_path / "audit.log")
    engine = LearningEngine(keyword_importance, calibration, audit_logger=logger)

    evidence = {"evidence_id": "ev1", "text": "Alpha beta signal"}
    engine.ingest_director_correction(evidence, predicted_kpa="KPA_1", corrected_kpa="KPA_2")

    assert keyword_importance["alpha"] > 0.1
    assert keyword_importance["beta"] > 0.0

    history = engine.get_learning_history()
    assert len(history) == 1
    assert history[0]["event"] == "director_correction"
    assert "alpha" in history[0]["delta"]
    assert "LEARNING_SIGNAL" in (tmp_path / "audit.log").read_text(encoding="utf-8")


def test_reflection_feedback_adjusts_weights_and_calibration(tmp_path):
    keyword_importance = {}
    calibration = {}
    engine = LearningEngine(keyword_importance, calibration, audit_logger=None, learning_rate=0.1)

    evidence = {"evidence_id": "ev2", "text": "gamma delta"}
    engine.ingest_reflection_feedback(evidence, tags_or_notes="note delta")

    assert keyword_importance["gamma"] > 0.0
    assert keyword_importance["delta"] > 0.0
    assert calibration["reflection_bias"] > 0.0
    assert engine.get_learning_history()
