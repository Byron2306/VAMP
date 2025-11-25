from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path
from typing import Dict, Mapping, Optional


class EvidenceRouter:
    """Route evidence files based on classification and policy rules."""

    def __init__(self, base_path: Path, director_queue_path: Path, policy_rules: Mapping[str, object]) -> None:
        self.base_path = Path(base_path)
        self.director_queue_path = Path(director_queue_path)
        self.policy_rules = policy_rules or {}
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.director_queue_path.mkdir(parents=True, exist_ok=True)

    def route(self, evidence: Mapping[str, object], classification: Mapping[str, object]) -> Dict[str, object]:
        evidence_id = self._extract_evidence_id(evidence)
        text = self._extract_text(evidence)
        file_path = Path(str(evidence.get("path") or evidence.get("file_path") or evidence.get("filepath")))

        reason: Optional[str] = None
        destination_parent: Path

        if self._is_policy_violation(text):
            reason = "POLICY_VIOLATION"
            destination_parent = self.director_queue_path
        elif float(classification.get("confidence", 0.0)) < 0.3:
            reason = "LOW_CONFIDENCE"
            destination_parent = self.director_queue_path
        elif classification.get("ambiguity"):
            reason = "AMBIGUOUS"
            destination_parent = self.director_queue_path
        else:
            kpa = classification.get("kpa") or "UNASSIGNED"
            destination_parent = self.base_path / str(kpa)

        destination_parent.mkdir(parents=True, exist_ok=True)

        filename = self._build_filename(
            classification.get("kpa") or "UNK",
            float(classification.get("confidence", 0.0)),
            evidence_id,
            file_path.suffix,
            reason,
        )
        destination = destination_parent / filename
        destination = self._resolve_conflict(destination)

        shutil.move(str(file_path), destination)

        return {
            "evidence_id": evidence_id,
            "destination": destination,
            "reason": reason,
            "routed_to": "director" if destination_parent == self.director_queue_path else "kpa",
            "kpa": classification.get("kpa"),
        }

    def _is_policy_violation(self, text: str) -> bool:
        tokens = self._tokenize(text)
        for rule in self.policy_rules.get("violations", []):
            keywords = []
            if isinstance(rule, str):
                keywords = [rule]
            elif isinstance(rule, Mapping):
                rule_keywords = rule.get("keywords")
                if isinstance(rule_keywords, (list, tuple, set)):
                    keywords = list(rule_keywords)
                elif isinstance(rule_keywords, str):
                    keywords = [rule_keywords]
            for keyword in keywords:
                if keyword.lower() in tokens:
                    return True
        return False

    def _build_filename(
        self,
        kpa: str,
        confidence: float,
        evidence_id: str,
        ext: str,
        reason: Optional[str],
    ) -> str:
        timestamp = int(time.time())
        identifier = self._sanitize(evidence_id)
        prefix = reason if reason else kpa
        name = f"[{prefix}]_{confidence:.2f}_{timestamp}_{identifier}{ext}"
        return self._apply_filename_constraints(name)

    def _resolve_conflict(self, path: Path) -> Path:
        candidate = path
        counter = 0
        while candidate.exists():
            digest = hashlib.sha256(candidate.name.encode()).hexdigest()[:8]
            stem = candidate.stem
            suffix = candidate.suffix
            counter += 1
            candidate = candidate.with_name(f"{stem}_{digest}_{counter}{suffix}")
        return candidate

    def _apply_filename_constraints(self, filename: str, max_length: int = 255) -> str:
        if len(filename) <= max_length:
            return filename
        ext = Path(filename).suffix
        cutoff = max_length - len(ext)
        return f"{filename[:cutoff]}{ext}"

    def _sanitize(self, value: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value)
        return safe.strip("-") or "unknown"

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

    def _tokenize(self, text: str) -> set[str]:
        if not text:
            return set()
        return {token.lower() for token in str(text).split()}
