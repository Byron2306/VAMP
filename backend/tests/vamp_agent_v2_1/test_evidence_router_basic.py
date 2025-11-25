from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.vamp_agent_v2_1.evidence_router import EvidenceRouter


def _make_evidence(tmp_path: Path, name: str, text: str) -> dict:
    file_path = tmp_path / f"{name}.txt"
    file_path.write_text(text, encoding="utf-8")
    return {"id": name, "text": text, "path": file_path}


def test_policy_violation_routes_to_director(tmp_path):
    router = EvidenceRouter(tmp_path / "kpa", tmp_path / "director", {"violations": [{"keywords": ["forbidden"]}]})
    evidence = _make_evidence(tmp_path, "ev_policy", "This contains forbidden terms")
    classification = {"kpa": "KPA_1", "confidence": 0.9, "ambiguity": False}

    result = router.route(evidence, classification)

    assert result["reason"] == "POLICY_VIOLATION"
    assert result["destination"].parent == tmp_path / "director"
    assert result["destination"].exists()


def test_low_confidence_routes_to_director(tmp_path):
    router = EvidenceRouter(tmp_path / "kpa", tmp_path / "director", {"violations": []})
    evidence = _make_evidence(tmp_path, "ev_low", "benign content")
    classification = {"kpa": "KPA_2", "confidence": 0.2, "ambiguity": False}

    result = router.route(evidence, classification)

    assert result["reason"] == "LOW_CONFIDENCE"
    assert result["destination"].parent == tmp_path / "director"


def test_ambiguous_routes_to_director(tmp_path):
    router = EvidenceRouter(tmp_path / "kpa", tmp_path / "director", {"violations": []})
    evidence = _make_evidence(tmp_path, "ev_ambiguous", "unclear content")
    classification = {"kpa": "KPA_3", "confidence": 0.5, "ambiguity": True}

    result = router.route(evidence, classification)

    assert result["reason"] == "AMBIGUOUS"
    assert result["destination"].parent == tmp_path / "director"


def test_confident_routes_to_kpa_folder(tmp_path):
    router = EvidenceRouter(tmp_path / "kpa", tmp_path / "director", {"violations": []})
    evidence = _make_evidence(tmp_path, "ev_normal", "quality training update")
    classification = {"kpa": "KPA_1", "confidence": 0.95, "ambiguity": False}

    result = router.route(evidence, classification)

    assert result["reason"] is None
    assert result["destination"].parent == tmp_path / "kpa" / "KPA_1"
    assert result["destination"].name.startswith("[KPA_1]_0.95")
