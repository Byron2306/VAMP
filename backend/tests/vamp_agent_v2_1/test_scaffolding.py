"""Tests for vamp_agent_v2_1 scaffolding modules."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.vamp_agent_v2_1.audit_logger import AuditLogger
from backend.vamp_agent_v2_1.background_scheduler import BackgroundScheduler
from backend.vamp_agent_v2_1.config_loader import (
    load_device_profiles,
    load_kpa_config,
    load_policy_rules,
)
from backend.vamp_agent_v2_1.memory_dumper import MemoryDumper
from backend.vamp_agent_v2_1.performance_monitor import PerformanceMonitor
from backend.vamp_agent_v2_1.self_aware_state import SelfAwareState


def test_audit_logger_writes(tmp_path):
    log_path = tmp_path / "audit.log"
    logger = AuditLogger(log_path)
    logger.log("hello", {"foo": "bar"})
    assert log_path.read_text(encoding="utf-8").strip() == "hello | context={'foo': 'bar'}"


def test_self_aware_state_snapshot_and_increment():
    state = SelfAwareState()
    state.increment("processed_items", 2)
    state.increment("custom_metric")
    snapshot = state.snapshot()
    assert snapshot["processed_items"] == 2
    assert snapshot["custom_metrics"]["custom_metric"] == 1


def test_memory_dumper_round_trip(tmp_path):
    dumper = MemoryDumper(tmp_path)
    dumper.create_dump({"foo": "bar"}, label="test")
    assert dumper.load_dump("test") == {"foo": "bar"}
    assert dumper.latest_dump() is not None


def test_performance_monitor_snapshot_runs():
    monitor = PerformanceMonitor()
    snapshot = monitor.snapshot()
    assert isinstance(snapshot, dict)


def test_background_scheduler_executes_task():
    scheduler = BackgroundScheduler(max_queue_size=1)
    executed = []

    def task():
        executed.append(True)

    scheduler.start()
    try:
        assert scheduler.schedule(task)
        timeout = time.time() + 2
        while not executed and time.time() < timeout:
            time.sleep(0.05)
        assert executed
    finally:
        scheduler.stop()


def test_config_loader_reads_stub_files():
    assert load_kpa_config() == {}
    assert load_policy_rules() == {"violations": []}
    profiles = load_device_profiles()
    assert set(profiles) == {"workstation", "laptop", "low_power"}
