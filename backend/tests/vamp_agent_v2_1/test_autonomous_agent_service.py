"""Smoke tests for the autonomous agent service orchestration."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.vamp_agent_v2_1.autonomous_agent_service import AutonomousAgentService


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_autonomous_agent_service_routes_and_logs(tmp_path):
    kpa_base = tmp_path / "kpa"
    director_queue = tmp_path / "director"
    dump_dir = tmp_path / "dumps"
    audit_log = tmp_path / "audit.log"

    kpa_config_path = _write_json(
        tmp_path / "kpa_config.json",
        {
            "KPA_1": {"keywords": {"alpha": 1.0}},
            "KPA_2": {"keywords": {"beta": 1.0}},
        },
    )
    policy_rules_path = _write_json(tmp_path / "policy_rules.json", {"violations": ["breach"]})
    device_profiles_path = _write_json(
        tmp_path / "device_profiles.json",
        {"workstation": {"batch_size": 2, "max_cpu_percent": 95, "max_memory_percent": 95}},
    )

    service = AutonomousAgentService(
        kpa_base_path=kpa_base,
        director_queue_path=director_queue,
        dump_dir=dump_dir,
        kpa_config_path=kpa_config_path,
        policy_rules_path=policy_rules_path,
        device_profiles_path=device_profiles_path,
        audit_log_path=audit_log,
        base_batch_size=2,
        dump_every_n=2,
        dump_every_seconds=1,
    )

    try:
        evidence_alpha = tmp_path / "alpha.txt"
        evidence_beta = tmp_path / "beta.txt"
        evidence_policy = tmp_path / "policy.txt"

        evidence_alpha.write_text("alpha keyword present", encoding="utf-8")
        evidence_beta.write_text("beta keyword present", encoding="utf-8")
        evidence_policy.write_text("potential breach detected", encoding="utf-8")

        service.enqueue_evidence({"path": evidence_alpha, "evidence_id": "alpha"})
        service.enqueue_evidence({"path": evidence_beta, "evidence_id": "beta"})
        service.enqueue_evidence({"path": evidence_policy, "evidence_id": "policy"})

        processed = 0
        while service.evidence_queue:
            processed += service.run_once()

        service.flush_background_tasks(timeout=2)

        assert processed == 3

        kpa1_files = list((kpa_base / "KPA_1").glob("*.txt"))
        kpa2_files = list((kpa_base / "KPA_2").glob("*.txt"))
        director_files = list(director_queue.glob("*.txt"))

        assert len(kpa1_files) == 1
        assert len(kpa2_files) == 1
        assert len(director_files) == 1

        log_content = audit_log.read_text(encoding="utf-8")
        assert "classification" in log_content
        assert "routing" in log_content

        dumps = list(dump_dir.glob("state_dump_*.json"))
        assert dumps, "memory dump should be created after processing threshold"
    finally:
        service.graceful_shutdown()
