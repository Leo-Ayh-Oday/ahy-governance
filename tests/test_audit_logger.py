"""Audit Reporter 测试 — 不可篡改审计日志 + hash 链 + 合规导出"""

import json
import os
import tempfile

import pytest

from ahy_governance import (
    AuditReporter,
    AuditEntry,
    AuditEventType,
    get_auditor,
    log_audit,
)


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def reporter():
    r = AuditReporter()
    yield r
    r.reset()


@pytest.fixture
def populated_reporter(reporter):
    reporter.log(AuditEventType.AGENT_START, "Planner", {"task": "合同审查"}, session_id="s1")
    reporter.log(AuditEventType.AGENT_COMPLETE, "Planner", {"result": "OK", "tokens": 5000}, session_id="s1")
    reporter.log(AuditEventType.AGENT_START, "Executor", {"task": "生成报告"}, session_id="s1")
    reporter.log(AuditEventType.AGENT_ERROR, "Executor", {"error": "timeout"}, session_id="s1")
    reporter.log(AuditEventType.CONFLICT_DETECTED, "Governor", {"type": "fact_conflict"}, session_id="s2")
    return reporter


# ── Hash Chain Tests ────────────────────────────────────────────

class TestHashChain:
    def test_entry_has_hash(self, reporter):
        entry = reporter.log(AuditEventType.AGENT_START, "Agent1", {"task": "test"})
        assert entry.hash is not None
        assert len(entry.hash) == 64  # SHA-256 hex
        assert entry.index == 0

    def test_chain_links_sequential(self, reporter):
        e1 = reporter.log(AuditEventType.AGENT_START, "A", {})
        e2 = reporter.log(AuditEventType.AGENT_COMPLETE, "A", {})
        assert e1.index == 0
        assert e2.index == 1
        assert e1.hash != e2.hash

    def test_verify_integrity_passes(self, populated_reporter):
        assert populated_reporter.verify_integrity()

    def test_verify_integrity_empty(self, reporter):
        assert reporter.verify_integrity()

    def test_tamper_detection(self, populated_reporter):
        # Directly mutate an entry's data
        populated_reporter._entries[1].details["result"] = "TAMPERED"
        assert not populated_reporter.verify_integrity()

    def test_tamper_detection_returns_entries(self, populated_reporter):
        populated_reporter._entries[2].event_type = AuditEventType.CONFIG_CHANGE  # tamper
        tampered = populated_reporter.find_tampered()
        assert len(tampered) >= 1

    def test_hash_depends_on_previous(self, reporter):
        """Tampering an early entry breaks ALL subsequent hashes"""
        e1 = reporter.log(AuditEventType.AGENT_START, "A", {"step": 1})
        e2 = reporter.log(AuditEventType.AGENT_COMPLETE, "A", {"step": 2})
        e3 = reporter.log(AuditEventType.AGENT_START, "B", {"step": 3})

        # Tamper e1
        reporter._entries[0].details["step"] = 999
        tampered = reporter.find_tampered()
        # e1 hash is wrong, so e2's prev_hash is wrong, so e3's too
        assert len(tampered) >= 1


# ── Logging Tests ───────────────────────────────────────────────

class TestLogging:
    def test_log_returns_entry(self, reporter):
        entry = reporter.log(AuditEventType.AGENT_START, "Planner", {"task": "review"})
        assert isinstance(entry, AuditEntry)
        assert entry.event_type == AuditEventType.AGENT_START
        assert entry.agent_name == "Planner"
        assert entry.details == {"task": "review"}

    def test_log_increments_index(self, reporter):
        for i in range(5):
            e = reporter.log(AuditEventType.AGENT_START, f"Agent{i}", {})
            assert e.index == i

    def test_log_preserves_timestamp(self, reporter):
        e = reporter.log(AuditEventType.PIPELINE_START, "Orchestrator", {})
        assert e.timestamp is not None
        assert "T" in e.timestamp

    def test_entry_count(self, populated_reporter):
        assert populated_reporter.entry_count == 5

    def test_entry_to_dict(self, reporter):
        e = reporter.log(AuditEventType.HUMAN_OVERRIDE, "Admin", {"reason": "bug"}, session_id="s99")
        d = e.to_dict()
        assert d["event_type"] == "human_override"
        assert d["agent"] == "Admin"
        assert d["session_id"] == "s99"
        assert "hash" in d

    def test_all_event_types_loggable(self, reporter):
        for etype in AuditEventType:
            entry = reporter.log(etype, "TestAgent", {})
            assert entry.event_type == etype


# ── Query Tests ─────────────────────────────────────────────────

class TestQuery:
    def test_filter_by_agent(self, populated_reporter):
        results = populated_reporter.query(agent_name="Planner")
        assert len(results) == 2

    def test_filter_by_event_type(self, populated_reporter):
        results = populated_reporter.query(event_type=AuditEventType.AGENT_ERROR)
        assert len(results) == 1
        assert results[0].agent_name == "Executor"

    def test_filter_by_session(self, populated_reporter):
        results = populated_reporter.query(session_id="s2")
        assert len(results) == 1

    def test_filter_combined(self, populated_reporter):
        results = populated_reporter.query(
            agent_name="Planner", session_id="s1"
        )
        assert len(results) == 2

    def test_filter_no_match(self, populated_reporter):
        assert len(populated_reporter.query(agent_name="Ghost")) == 0

    def test_recent_entries(self, populated_reporter):
        recent = populated_reporter.recent(3)
        assert len(recent) == 3
        assert recent[0].index > recent[-1].index


# ── Compliance Export Tests ─────────────────────────────────────

class TestComplianceExport:
    def test_export_soc2_structure(self, populated_reporter):
        report = populated_reporter.export_soc2()
        assert report["framework"] == "SOC2"
        assert "generated_at" in report
        assert "controls" in report
        assert "security" in report["controls"]
        assert "availability" in report["controls"]
        assert "confidentiality" in report["controls"]
        assert "total_events" in report
        assert report["chain_verified"] is True
        assert "audit_trail_hash" in report

    def test_export_iso27001_structure(self, populated_reporter):
        report = populated_reporter.export_iso27001()
        assert report["framework"] == "ISO27001"
        assert "generated_at" in report
        assert "annex_a_controls" in report
        assert "A.9" in report["annex_a_controls"]   # Access control
        assert "A.12" in report["annex_a_controls"]  # Operations security
        assert "A.16" in report["annex_a_controls"]  # Incident management
        assert "total_events" in report
        assert report["chain_verified"] is True

    def test_compliance_empty_log(self, reporter):
        report = reporter.export_soc2()
        assert report["total_events"] == 0
        assert report["chain_verified"] is True

    def test_compliance_tampered_fails(self, populated_reporter):
        populated_reporter._entries[0].details["result"] = "TAMPERED"
        report = populated_reporter.export_soc2()
        assert report["chain_verified"] is False


# ── Export Tests ────────────────────────────────────────────────

class TestExport:
    def test_export_csv(self, populated_reporter):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "audit.csv")
            populated_reporter.export_csv(path)
            assert os.path.exists(path)
            with open(path) as f:
                lines = f.readlines()
            assert len(lines) == 6  # header + 5 entries
            assert "index,event_type,agent,session_id,timestamp,hash" in lines[0]

    def test_export_json(self, populated_reporter):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "audit.json")
            populated_reporter.export_json(path)
            assert os.path.exists(path)
            with open(path) as f:
                data = json.load(f)
            assert len(data) == 5
            assert "hash" in data[0]

    def test_export_empty(self, reporter):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "empty.csv")
            reporter.export_csv(path)
            with open(path) as f:
                content = f.read()
            assert "index,event_type" in content


# ── Edge Cases ──────────────────────────────────────────────────

class TestEdgeCases:
    def test_large_log(self, reporter):
        for i in range(500):
            reporter.log(AuditEventType.AGENT_START, f"Agent{i % 10}", {"iter": i})
        assert reporter.entry_count == 500
        assert reporter.verify_integrity()

    def test_reset_clears_all(self, populated_reporter):
        populated_reporter.reset()
        assert populated_reporter.entry_count == 0
        assert populated_reporter.verify_integrity()

    def test_entry_with_no_details(self, reporter):
        e = reporter.log(AuditEventType.PIPELINE_COMPLETE, "Orch", {})
        assert e.details == {}

    def test_entry_with_complex_details(self, reporter):
        details = {
            "nested": {"key": "value", "list": [1, 2, 3]},
            "unicode": "中文测试",
            "null_value": None,
            "bool": True,
        }
        e = reporter.log(AuditEventType.CONFIG_CHANGE, "Admin", details)
        retrieved = reporter.query(agent_name="Admin")[0]
        assert retrieved.details == details

    def test_hash_deterministic(self):
        """Same data at same index with same prev_hash = same entry hash"""
        ts = "2026-05-07T00:00:00+00:00"
        r1 = AuditReporter()
        r2 = AuditReporter()
        e1 = r1.log(AuditEventType.AGENT_START, "X", {"a": 1}, timestamp=ts)
        e2 = r2.log(AuditEventType.AGENT_START, "X", {"a": 1}, timestamp=ts)
        assert e1.hash == e2.hash

    def test_all_event_types_have_values(self):
        """确保 AuditEventType 包含完整的 Agent 生命周期事件"""
        values = {e.value for e in AuditEventType}
        assert "agent_start" in values
        assert "agent_complete" in values
        assert "agent_error" in values
        assert "pipeline_start" in values
        assert "pipeline_complete" in values
        assert "conflict_detected" in values
        assert "budget_exceeded" in values
        assert "human_override" in values


# ── Convenience Functions ───────────────────────────────────────

class TestConvenienceFunctions:
    def test_log_audit_global(self):
        r = get_auditor()
        r.reset()
        entry = log_audit(AuditEventType.AGENT_START, "GlobalAgent", {"x": 1})
        assert entry.agent_name == "GlobalAgent"
        assert r.entry_count == 1
        r.reset()

    def test_get_auditor_singleton(self):
        a1 = get_auditor()
        a2 = get_auditor()
        assert a1 is a2
        a1.reset()


# ── AuditEntry Tests ────────────────────────────────────────────

class TestAuditEntry:
    def test_entry_repr(self, reporter):
        e = reporter.log(AuditEventType.AGENT_START, "Test", {"a": 1})
        r = repr(e)
        assert "Test" in r
        assert "agent_start" in r
