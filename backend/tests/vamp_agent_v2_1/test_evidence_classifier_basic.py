from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.vamp_agent_v2_1.evidence_classifier import EvidenceClassifier


def test_classifier_scores_and_ambiguity():
    kpa_config = {
        "KPA_1": {"keywords": {"safety": 1.0, "training": 0.5}},
        "KPA_2": {"keywords": {"policy": 1.0}},
        "KPA_3": {"keywords": ["quality"]},
    }
    classifier = EvidenceClassifier(kpa_config, keyword_importance={"policy": 0.5}, calibration=0.8)

    evidence = {"id": "EV1", "text": "Safety policy update with quality training"}
    result = classifier.classify(evidence)

    assert result["kpa"] == "KPA_1"
    assert result["ambiguity"] is True
    assert result["confidence"] == 0.8
    assert result["scores"]["KPA_1"] == 1.0
    assert result["scores"]["KPA_2"] == 1.0
    assert "KPA_1:safety" in result["reasons"]
    assert "KPA_3:quality" in result["reasons"]


def test_classifier_handles_empty_text():
    classifier = EvidenceClassifier({}, calibration=1.0)
    result = classifier.classify({"id": "EMPTY", "text": ""})

    assert result["kpa"] is None
    assert result["confidence"] == 0.0
    assert result["ambiguity"] is True
    assert all(score == 0.0 for score in result["scores"].values())
