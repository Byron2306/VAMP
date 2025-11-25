from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.vamp_agent_v2_1.audit_logger import AuditLogger
from backend.vamp_agent_v2_1.self_aware_state import SelfAwareState


def test_self_aware_state_tracks_metrics(tmp_path):
    logger = AuditLogger(tmp_path / "audit.log")
    state = SelfAwareState(audit_logger=logger, rolling_window=3)

    state.update_after_classification({"kpa": "KPA_1"}, approved=True)
    state.update_after_classification({"kpa": "KPA_2"}, approved=False)
    state.update_after_classification({"kpa": "KPA_3"}, approved=None)

    snapshot = state.to_dict()
    assert snapshot["evidence_processed_count"] == 3
    assert snapshot["approvals"] == 1
    assert snapshot["corrections"] == 1
    assert snapshot["pending_reviews"] == 1
    assert snapshot["accuracy_estimate"] == 0.5
    assert snapshot["rolling_accuracy"] == 0.5

    state.update_after_error("timeout")
    snapshot = state.to_dict()
    assert snapshot["error_count"] == 1
    assert snapshot["errors_by_type"]["timeout"] == 1

    log_content = (tmp_path / "audit.log").read_text(encoding="utf-8")
    assert "STATE_SNAPSHOT" in log_content
