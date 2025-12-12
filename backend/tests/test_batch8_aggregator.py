import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.batch8_aggregator import (
    ArtefactScore,
    Batch8Input,
    KPA,
    KPI,
    PerformanceContract,
    aggregate_batch8,
    export_final_summary_csv,
)


RATING_BANDS = [
    {"min": 0.85, "max": 1.0, "rating": 5, "label": "Outstanding"},
    {"min": 0.70, "max": 0.84, "rating": 4, "label": "Exceeds Expectations"},
    {"min": 0.55, "max": 0.69, "rating": 3, "label": "Meets Expectations"},
    {"min": 0.40, "max": 0.54, "rating": 2, "label": "Partially Meets"},
    {"min": 0.0, "max": 0.39, "rating": 1, "label": "Does Not Meet"},
]

TIER_RULES = [
    {"name": "Transformational", "conditions": {"min_rating": 4, "no_kpa_below": 0.6}},
    {"name": "Developmental", "conditions": {"rating_equals": 3, "all_kpa_at_least": 0.5}},
    {"name": "Compliance / Needs Improvement", "conditions": {"any_kpa_below": 0.4}},
]

SCORING_CONFIG = {
    "rating_bands": RATING_BANDS,
    "tier_rules": TIER_RULES,
    "confidence_thresholds": {"confidence": 0.5, "credibility": 0.7},
}


def _simple_contract(weight1=100, weight2=0):
    kpi1 = KPI(code="KPA1_KPI_01", name="Design")
    kpa1 = KPA(code="KPA1", name="Teaching and Learning", weight_pct=weight1, kpis=[kpi1])
    if weight2:
        kpi2 = KPI(code="KPA2_KPI_01", name="OHS")
        kpa2 = KPA(code="KPA2", name="OHS", weight_pct=weight2, kpis=[kpi2])
        return PerformanceContract(kpas=[kpa1, kpa2])
    return PerformanceContract(kpas=[kpa1])


def test_strong_artefact_completes_kpi(tmp_path):
    contract = _simple_contract()
    artefact = ArtefactScore(
        id="a1",
        matched_kpis=["KPA1_KPI_01"],
        completion_estimate=1.0,
        evidence_credibility_weight=1.0,
        confidence=1.0,
    )
    summaries, final = aggregate_batch8(
        Batch8Input(contract=contract, artefact_scores=[artefact], scoring_config=SCORING_CONFIG)
    )

    assert summaries[0].kcr == 1.0
    assert summaries[0].status == "ACHIEVED"
    assert final.final_rating == 5

    csv_path = tmp_path / "final.csv"
    export_final_summary_csv(csv_path, summaries, final)
    assert csv_path.exists()


def test_many_weak_artefacts_partially_complete_kpi():
    contract = _simple_contract()
    artefacts = [
        ArtefactScore(
            id=f"weak{i}",
            matched_kpis=["KPA1_KPI_01"],
            completion_estimate=0.5,
            evidence_credibility_weight=0.8,
            confidence=0.5,
        )
        for i in range(3)
    ]
    summaries, _ = aggregate_batch8(
        Batch8Input(contract=contract, artefact_scores=artefacts, scoring_config=SCORING_CONFIG)
    )

    assert math.isclose(summaries[0].kcr, 0.6, rel_tol=1e-3)
    assert summaries[0].status == "PARTIALLY ACHIEVED"


def test_low_credibility_evidence_capped():
    contract = _simple_contract()
    artefact = ArtefactScore(
        id="screenshot",
        matched_kpis=["KPA1_KPI_01"],
        completion_estimate=1.0,
        evidence_credibility_weight=0.4,
        confidence=1.0,
        evidence_type="screenshot",
    )
    summaries, _ = aggregate_batch8(
        Batch8Input(contract=contract, artefact_scores=[artefact], scoring_config=SCORING_CONFIG)
    )

    assert summaries[0].kcr == 0.4
    assert summaries[0].status == "INSUFFICIENT_EVIDENCE"


def test_missing_kpis_flagged_for_review():
    contract = PerformanceContract(kpas=[KPA(code="KPA1", name="Teaching", weight_pct=100, kpis=[])])
    summaries, _ = aggregate_batch8(
        Batch8Input(contract=contract, artefact_scores=[], scoring_config=SCORING_CONFIG)
    )

    assert summaries[0].status == "NEEDS_REVIEW_MISSING_KPIS"
    assert summaries[0].kcr == 0.0


def test_tier_blocks_on_weak_kpa():
    contract = _simple_contract(weight1=70, weight2=30)
    artefacts = [
        ArtefactScore(
            id="strong",
            matched_kpis=["KPA1_KPI_01"],
            completion_estimate=1.0,
            evidence_credibility_weight=1.0,
            confidence=1.0,
        ),
        ArtefactScore(
            id="weak",
            matched_kpis=["KPA2_KPI_01"],
            completion_estimate=0.3,
            evidence_credibility_weight=0.6,
            confidence=0.5,
        ),
    ]
    summaries, final = aggregate_batch8(
        Batch8Input(contract=contract, artefact_scores=artefacts, scoring_config=SCORING_CONFIG)
    )

    kpa_scores = {s.kpa_code: s.kcr for s in summaries}
    assert kpa_scores["KPA2"] < 0.6
    assert final.final_rating >= 4
    assert final.final_tier != "Transformational"
