"""Configuration loading helpers for Autonomous Agent v2.1."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


PACKAGE_ROOT = Path(__file__).resolve().parent


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as config_file:
        return json.load(config_file)


def load_kpa_config() -> Dict[str, Any]:
    """Load keyword configuration for KPA classification."""

    return _load_json(PACKAGE_ROOT / "config" / "kpa_keywords.json")


def load_policy_rules() -> Dict[str, Any]:
    """Load policy violation rules for director routing."""

    return _load_json(PACKAGE_ROOT / "config" / "policy_rules.json")


def load_device_profiles() -> Dict[str, Any]:
    """Load device resource profiles for scheduling and throttling."""

    return _load_json(PACKAGE_ROOT / "config" / "device_profiles.json")
