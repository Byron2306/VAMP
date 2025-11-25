#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
evidence_transformer.py — Transform raw VAMP scan output into scored, tiered evidence.

Phase 2 of PDF Implementation Roadmap.

This module handles:
- KPA classification via keyword matching
- Evidence tiering (Compliance / Developmental / Transformational)
- Policy validation
- Confidence scoring
- Cross-platform deduplication
"""

from __future__ import annotations
import json
import hashlib
from typing import Any, Dict, List, Optional, Tuple, Set
from pathlib import Path
from datetime import datetime


class EvidenceTransformer:
    """Transform raw VAMP evidence into scored, tiered, policy-checked form."""

    def __init__(
        self,
        kpa_config_path: Optional[str] = None,
        tier_keywords_path: Optional[str] = None,
        policy_registry_path: Optional[str] = None,
    ):
        """Initialize transformer with configuration files."""
        self.kpa_keywords: Dict[str, List[Tuple[str, float]]] = {}
        self.tier_keywords: Dict[str, List[str]] = {}
        self.policy_registry: Dict[str, Dict] = {}
        self.seen_hashes: Set[str] = set()

        # Load KPA configuration
        if kpa_config_path and Path(kpa_config_path).exists():
            try:
                with open(kpa_config_path) as f:
                    config = json.load(f)
                    for kpa, keywords in config.items():
                        # keywords can be list of strings (importance 1.0) or list of [keyword, importance]
                        self.kpa_keywords[kpa] = []
                        for item in keywords:
                            if isinstance(item, str):
                                self.kpa_keywords[kpa].append((item, 1.0))
                            elif isinstance(item, list):
                                self.kpa_keywords[kpa].append(tuple(item))
            except Exception as e:
                print(f"[WARNING] Failed to load KPA config: {e}")

        # Load tier keywords
        if tier_keywords_path and Path(tier_keywords_path).exists():
            try:
                with open(tier_keywords_path) as f:
                    self.tier_keywords = json.load(f)
            except Exception as e:
                print(f"[WARNING] Failed to load tier keywords: {e}")

        # Load policy registry
        if policy_registry_path and Path(policy_registry_path).exists():
            try:
                with open(policy_registry_path) as f:
                    self.policy_registry = json.load(f)
            except Exception as e:
                print(f"[WARNING] Failed to load policy registry: {e}")

    def transform(self, vamp_item: Dict[str, Any]) -> Dict[str, Any]:
        """Transform a raw VAMP scan result into scored, tiered evidence."""
        if not isinstance(vamp_item, dict):
            return self._safe_default()

        # Skip if already transformed
        if vamp_item.get("_transformed"):
            return dict(vamp_item)

        # Deduplicate by hash
        item_hash = vamp_item.get("hash") or self._compute_hash(vamp_item)
        if item_hash in self.seen_hashes:
            return {**vamp_item, "_duplicate": True, "hash": item_hash}
        self.seen_hashes.add(item_hash)

        out = dict(vamp_item)
        out["hash"] = item_hash

        # Step 1: Classify KPA
        text_for_classification = self._extract_text(vamp_item)
        kpa_scores = self._classify_kpa(text_for_classification)
        out["kpa"] = [kpa for kpa, _ in kpa_scores]
        out["kpa_scores"] = dict(kpa_scores)

        # Step 2: Classify tier
        tiers = self._classify_tier(vamp_item, out["kpa"])
        out["tier"] = tiers

        # Step 3: Check policies
        policy_hits = self._check_policies(text_for_classification, out["kpa"])
        out["policy_hits"] = policy_hits
        out["must_pass_risks"] = [p for p in policy_hits if self._is_must_pass_policy(p)]

        # Step 4: Compute confidence
        out["confidence"] = self._compute_confidence(kpa_scores)

        # Step 5: Add metadata
        out["_transformed"] = True
        out["_transform_timestamp"] = datetime.utcnow().isoformat()
        out["_transform_version"] = "1.0"

        return out

    def _extract_text(self, item: Dict[str, Any]) -> str:
        """Extract all searchable text from an evidence item."""
        parts = []
        for key in ["title", "subject", "body", "preview", "path"]:
            if key in item and item[key]:
                parts.append(str(item[key]).lower())
        return " ".join(parts).strip()

    def _classify_kpa(self, text: str) -> List[Tuple[str, float]]:
        """Classify evidence into KPA categories with confidence."""
        scores: Dict[str, float] = {}

        for kpa, keywords in self.kpa_keywords.items():
            score = 0.0
            for keyword, importance in keywords:
                if keyword.lower() in text:
                    score += importance
            if score > 0:
                scores[kpa] = min(score / max(len(keywords), 1), 1.0)

        # Return sorted by score, descending
        return sorted(scores.items(), key=lambda x: -x[1])

    def _classify_tier(self, item: Dict[str, Any], kpas: List[str]) -> List[str]:
        """Classify evidence tier based on content and KPA."""
        text = self._extract_text(item).lower()
        tiers = set()

        for tier_name, keywords in self.tier_keywords.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    tiers.add(tier_name)

        return sorted(list(tiers)) or ["Developmental"]  # Default tier

    def _check_policies(self, text: str, kpas: List[str]) -> List[str]:
        """Check evidence against policy registry."""
        hits = []

        for policy_id, policy_config in self.policy_registry.items():
            keywords = policy_config.get("keywords", [])
            for keyword in keywords:
                if keyword.lower() in text:
                    hits.append(policy_id)
                    break

        return hits

    def _is_must_pass_policy(self, policy_id: str) -> bool:
        """Check if a policy is a must-pass (critical) policy."""
        if policy_id not in self.policy_registry:
            return False
        return self.policy_registry[policy_id].get("must_pass", False)

    def _compute_confidence(self, kpa_scores: List[Tuple[str, float]]) -> float:
        """Compute overall confidence score."""
        if not kpa_scores:
            return 0.0
        # Use top score as confidence
        return kpa_scores[0][1] if kpa_scores else 0.0

    def _compute_hash(self, item: Dict[str, Any]) -> str:
        """Compute SHA256 hash for deduplication."""
        key_fields = ["source", "path", "hash", "title", "timestamp"]
        combined = "".join(
            str(item.get(field, "")) for field in key_fields
        )
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def _safe_default(self) -> Dict[str, Any]:
        """Return safe default transformed object."""
        return {
            "kpa": [],
            "tier": ["Developmental"],
            "policy_hits": [],
            "must_pass_risks": [],
            "confidence": 0.0,
            "_transformed": True,
            "_transform_timestamp": datetime.utcnow().isoformat(),
        }

    def batch_transform(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Transform multiple evidence items."""
        return [self.transform(item) for item in items]

    def reset_seen_hashes(self) -> None:
        """Clear deduplication cache for new batch."""
        self.seen_hashes.clear()


__all__ = ["EvidenceTransformer"]
