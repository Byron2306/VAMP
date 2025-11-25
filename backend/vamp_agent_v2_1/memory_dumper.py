"""State snapshot utilities for Autonomous Agent v2.1.

MemoryDumper is responsible for persisting periodic snapshots of agent state
and weights. This scaffolding focuses on API shape; durability and integrity
features will be added in later stages.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


class MemoryDumper:
    """Handle creation and retrieval of append-only memory dumps."""

    def __init__(self, dump_dir: Path) -> None:
        self.dump_dir = Path(dump_dir)
        self.dump_dir.mkdir(parents=True, exist_ok=True)

    def create_dump(self, state: Dict[str, Any], label: str) -> Path:
        """Persist the provided state under a label.

        TODO: add hashing, retention policies, and verification hooks.
        """

        dump_path = self.dump_dir / f"{label}.json"
        with dump_path.open("w", encoding="utf-8") as dump_file:
            json.dump(state, dump_file, indent=2, sort_keys=True)
        return dump_path

    def load_dump(self, label: str) -> Dict[str, Any]:
        """Load a previously created dump.

        Returns an empty dict when the label does not exist to avoid raising
        exceptions during recovery attempts.
        """

        dump_path = self.dump_dir / f"{label}.json"
        if not dump_path.exists():
            return {}

        with dump_path.open("r", encoding="utf-8") as dump_file:
            return json.load(dump_file)

    def latest_dump(self) -> Path | None:
        """Return the most recent dump path if available."""

        dumps = sorted(self.dump_dir.glob("*.json"))
        return dumps[-1] if dumps else None
