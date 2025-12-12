from __future__ import annotations

"""Batch 8 deterministic aggregation engine.

This module converts artefact-level scores into KPI/KPA performance
summaries and final NWU-style ratings. The logic is intentionally
transparent and reproducible to satisfy HR audit requirements.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# --------------------
# Data structures
# --------------------


@dataclass
class KPI:
    code: str
    name: str
    permitted_evidence_types: Optional[List[str]] = None


@dataclass
class KPA:
    code: str
    name: str
    weight_pct: float
    kpis: List[KPI] = field(default_factory=list)


@dataclass
class PerformanceContract:
    kpas: List[KPA]


@dataclass
class ArtefactScore:
    id: str
    matched_kpis: List[str]
    completion_estimate: float
    evidence_credibility_weight: float
    confidence: float
    status: str = "SCORED"
    extract_status: str = "success"
    evidence_type: str = "document"


@dataclass
class Batch8Input:
    contract: PerformanceContract
    artefact_scores: List[ArtefactScore]
    scoring_config: Dict


@dataclass
class KPASummary:
    kpa_code: str
    kpa_name: str
    weight_pct: float
    kcr: float
    status: str
    contributing_artefacts: int


@dataclass
class FinalPerformance:
    overall_score: float
    final_rating: int
    final_tier: str
    justification: str


# --------------------
# Constants
# --------------------

_KPI_STATUS_THRESHOLDS: List[Tuple[float, float, str]] = [
    (0.8, 1.0, "ACHIEVED"),
    (0.5, 0.79, "PARTIALLY ACHIEVED"),
    (0.0, 0.49, "NOT ACHIEVED"),
]

_KPA_STATUS_OVERRIDE_PRIORITY = [
    "NEEDS_REVIEW_MISSING_KPIS",
    "INSUFFICIENT_EVIDENCE",
]


# --------------------
# Core calculations
# --------------------


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _compute_acs(artefact: ArtefactScore) -> float:
    """Compute Artefact Contribution Score (ACS)."""
    if artefact.status != "SCORED":
        return 0.0
    base = artefact.completion_estimate * artefact.evidence_credibility_weight * artefact.confidence
    base = _clamp(base)
    if artefact.evidence_credibility_weight < 0.5:
        base = min(base, 0.4)
    return base


def _eligible_for_kpi(artefact: ArtefactScore, kpi: KPI) -> bool:
    if artefact.status == "UNSCORABLE":
        return False
    if artefact.extract_status == "failed":
        return False
    if kpi.permitted_evidence_types:
        return artefact.evidence_type in kpi.permitted_evidence_types
    return True


def _kpi_status(kcs: float) -> str:
    for low, high, label in _KPI_STATUS_THRESHOLDS:
        if low <= kcs <= high:
            return label
    return "NOT ACHIEVED"


def _kpa_status(kcr: float) -> str:
    return _kpi_status(kcr)


def _evaluate_tier(rating: int, kpa_scores: Dict[str, float], tier_rules: List[Dict]) -> str:
    for rule in tier_rules:
        cond = rule.get("conditions", {})
        name = rule.get("name") or ""
        if not name:
            continue
        if not _tier_condition_matches(cond, rating, kpa_scores):
            continue
        return name
    return "Unspecified"


def _tier_condition_matches(cond: Dict, rating: int, kpa_scores: Dict[str, float]) -> bool:
    if "min_rating" in cond and rating < cond["min_rating"]:
        return False
    if "rating_equals" in cond and rating != cond["rating_equals"]:
        return False
    if "no_kpa_below" in cond:
        threshold = cond["no_kpa_below"]
        if any(score < threshold for score in kpa_scores.values()):
            return False
    if "min_kpa" in cond:
        threshold = cond["min_kpa"]
        if any(score < threshold for score in kpa_scores.values()):
            return False
    if "any_kpa_below" in cond:
        threshold = cond["any_kpa_below"]
        if not any(score < threshold for score in kpa_scores.values()):
            return False
    if "all_kpa_at_least" in cond:
        threshold = cond["all_kpa_at_least"]
        if any(score < threshold for score in kpa_scores.values()):
            return False
    return True


def _rating_from_bands(ocs: float, bands: List[Dict]) -> Tuple[int, str]:
    best_rating = 0
    best_label = "Unrated"
    for band in bands:
        min_v = band.get("min", 0)
        max_v = band.get("max", 1)
        rating = int(band.get("rating", 0))
        label = band.get("label", "")
        if min_v <= ocs <= max_v and rating >= best_rating:
            best_rating = rating
            best_label = label or best_label
    return best_rating, best_label


def _build_justification(rating_label: str, kpa_summaries: List[KPASummary]) -> str:
    parts = [f"The staff member achieved an overall performance rating of {rating_label}."]
    status_phrases = {
        "ACHIEVED": "was achieved based on submitted evidence",
        "PARTIALLY ACHIEVED": "was partially achieved with limited supporting evidence",
        "NOT ACHIEVED": "was not achieved",
        "INSUFFICIENT_EVIDENCE": "lacked sufficient evidence and was capped",
        "NEEDS_REVIEW_MISSING_KPIS": "requires review due to missing KPIs",
    }
    for summary in sorted(kpa_summaries, key=lambda s: s.kpa_code):
        phrase = status_phrases.get(summary.status, f"has status {summary.status}")
        parts.append(
            f"{summary.kpa_name} ({summary.weight_pct:.0f}% weighting) {phrase}."
        )
    return " ".join(parts)


# --------------------
# Public API
# --------------------


def aggregate_batch8(batch_input: Batch8Input) -> Tuple[List[KPASummary], FinalPerformance]:
    contract = batch_input.contract
    artefacts = batch_input.artefact_scores
    cfg = batch_input.scoring_config or {}
    rating_bands = cfg.get("rating_bands", [])
    tier_rules = cfg.get("tier_rules", [])
    confidence_thresholds = cfg.get("confidence_thresholds", {})
    conf_threshold = confidence_thresholds.get("confidence", 0.5)
    cred_threshold = confidence_thresholds.get("credibility", 0.7)

    kpi_map: Dict[str, KPI] = {kpi.code: kpi for kpa in contract.kpas for kpi in kpa.kpis}
    # Group artefacts per KPI with eligibility filtering
    kpi_evidence: Dict[str, List[Tuple[ArtefactScore, float]]] = {kpi_code: [] for kpi_code in kpi_map}
    kpa_evidence_meta: Dict[str, List[ArtefactScore]] = {kpa.code: [] for kpa in contract.kpas}

    for artefact in artefacts:
        acs = _compute_acs(artefact)
        for kpi_code in artefact.matched_kpis:
            kpi = kpi_map.get(kpi_code)
            if not kpi:
                continue
            kpa_code = _find_kpa_for_kpi(contract, kpi_code)
            if kpa_code:
                kpa_evidence_meta[kpa_code].append(artefact)
            if not _eligible_for_kpi(artefact, kpi):
                continue
            kpi_evidence[kpi_code].append((artefact, acs))

    kpi_scores: Dict[str, float] = {}

    for kpi_code, artefact_list in kpi_evidence.items():
        total_acs = sum(acs for _, acs in artefact_list)
        kcs = _clamp(total_acs)
        kpi_scores[kpi_code] = kcs

    kpa_summaries: List[KPASummary] = []
    kpa_scores: Dict[str, float] = {}

    for kpa in contract.kpas:
        if not kpa.kpis:
            kcr = 0.0
            status = "NEEDS_REVIEW_MISSING_KPIS"
        else:
            kcs_values = [kpi_scores.get(kpi.code, 0.0) for kpi in kpa.kpis]
            kcr = sum(kcs_values) / len(kcs_values) if kcs_values else 0.0
            status = _kpa_status(kcr)

        evidence_meta = kpa_evidence_meta.get(kpa.code, [])
        if status not in _KPA_STATUS_OVERRIDE_PRIORITY:
            has_confidence = any(a.confidence >= conf_threshold for a in evidence_meta)
            has_credibility = any(
                a.evidence_credibility_weight >= cred_threshold for a in evidence_meta
            )
            if not has_confidence or not has_credibility:
                status = "INSUFFICIENT_EVIDENCE"
                kcr = min(kcr, 0.49)

        kpa_scores[kpa.code] = kcr
        contributing = len({a.id for a in evidence_meta if _compute_acs(a) > 0})

        kpa_summaries.append(
            KPASummary(
                kpa_code=kpa.code,
                kpa_name=kpa.name,
                weight_pct=kpa.weight_pct,
                kcr=round(kcr, 4),
                status=_apply_status_overrides(status),
                contributing_artefacts=contributing,
            )
        )

    ocs = sum(summary.kcr * (summary.weight_pct / 100.0) for summary in kpa_summaries)
    rating, rating_label = _rating_from_bands(ocs, rating_bands)
    tier = _evaluate_tier(rating, kpa_scores, tier_rules)
    justification = _build_justification(f"{rating} ({rating_label})", kpa_summaries)

    final = FinalPerformance(
        overall_score=round(ocs, 4),
        final_rating=rating,
        final_tier=tier,
        justification=justification,
    )

    return kpa_summaries, final


def _apply_status_overrides(status: str) -> str:
    if status in _KPA_STATUS_OVERRIDE_PRIORITY:
        return status
    return status


def _find_kpa_for_kpi(contract: PerformanceContract, kpi_code: str) -> Optional[str]:
    for kpa in contract.kpas:
        for kpi in kpa.kpis:
            if kpi.code == kpi_code:
                return kpa.code
    return None


def export_final_summary_csv(
    filepath,
    kpa_summaries: List[KPASummary],
    final: FinalPerformance,
):
    import csv
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["KPA", "Weight %", "Completion %", "Status", "Artefact Count"])
        for summary in kpa_summaries:
            writer.writerow(
                [
                    summary.kpa_name,
                    f"{summary.weight_pct:.0f}",
                    f"{summary.kcr * 100:.2f}",
                    summary.status,
                    summary.contributing_artefacts,
                ]
            )
        writer.writerow(
            [
                "OVERALL",
                "100",
                f"{final.overall_score * 100:.2f}",
                final.final_tier,
                "-",
            ]
        )


__all__ = [
    "KPI",
    "KPA",
    "PerformanceContract",
    "ArtefactScore",
    "Batch8Input",
    "KPASummary",
    "FinalPerformance",
    "aggregate_batch8",
    "export_final_summary_csv",
]
