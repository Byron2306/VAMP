from __future__ import annotations

import re
from typing import Dict, Iterable, List, Mapping, Optional


class EvidenceClassifier:
    """Deterministic keyword-based classifier for KPA routing."""

    def __init__(
        self,
        kpa_config: Mapping[str, Mapping[str, object]],
        keyword_importance: Optional[Mapping[str, float]] = None,
        calibration: Optional[float] = None,
    ) -> None:
        self.kpa_config = dict(kpa_config)
        self.keyword_importance = {k.lower(): float(v) for k, v in (keyword_importance or {}).items()}
        self.calibration_factor = calibration if calibration is not None else 1.0

    def classify(self, evidence: Mapping[str, object]) -> Dict[str, object]:
        evidence_id = self._extract_evidence_id(evidence)
        text = self._extract_text(evidence)
        tokens = self._tokenize(text)

        kpa_keys = set(self.kpa_config) | {"KPA_1", "KPA_2", "KPA_3"}
        raw_scores = {kpa: 0.0 for kpa in kpa_keys}
        reasons: List[str] = []

        for kpa, weights in self._iter_kpa_weights():
            score = 0.0
            for token in tokens:
                if token in weights:
                    weight = weights[token] + self.keyword_importance.get(token, 0.0)
                    score += weight
                    reasons.append(f"{kpa}:{token}")
            raw_scores[kpa] = score

        max_raw = max(raw_scores.values()) if raw_scores else 0.0
        if max_raw <= 0.0:
            return {
                "evidence_id": evidence_id,
                "kpa": None,
                "scores": {k: 0.0 for k in sorted(kpa_keys)},
                "confidence": 0.0,
                "ambiguity": True,
                "reasons": [],
            }

        normalized_scores = {kpa: score / max_raw for kpa, score in raw_scores.items()}
        top_kpa, top_score = self._top_kpa(normalized_scores)
        second_score = self._second_score(normalized_scores, top_kpa)
        ambiguity = (top_score - second_score) < 0.10 if len(normalized_scores) > 1 else False

        confidence = max(0.0, min(top_score * self.calibration_factor, 1.0))

        return {
            "evidence_id": evidence_id,
            "kpa": top_kpa,
            "scores": {k: normalized_scores.get(k, 0.0) for k in sorted(kpa_keys)},
            "confidence": confidence,
            "ambiguity": ambiguity,
            "reasons": reasons,
        }

    def _iter_kpa_weights(self) -> Iterable[tuple[str, Dict[str, float]]]:
        for kpa, entry in self.kpa_config.items():
            keywords = entry.get("keywords") if isinstance(entry, Mapping) and "keywords" in entry else entry
            if isinstance(keywords, Mapping):
                yield kpa, {str(k).lower(): float(v) for k, v in keywords.items()}
            elif isinstance(keywords, (list, tuple, set)):
                yield kpa, {str(k).lower(): 1.0 for k in keywords}
            else:
                yield kpa, {}

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
        return re.findall(r"\b\w+\b", text.lower())

    def _top_kpa(self, scores: Mapping[str, float]) -> tuple[str, float]:
        sorted_scores = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        return sorted_scores[0]

    def _second_score(self, scores: Mapping[str, float], top_kpa: str) -> float:
        sorted_scores = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        for kpa, score in sorted_scores:
            if kpa != top_kpa:
                return score
        return 0.0
