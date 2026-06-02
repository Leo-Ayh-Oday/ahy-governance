"""Tests for Recovery Learner — 自愈规则学习 Agent."""

from ahy_governance.recovery_learner import (
    RecoveryLearner, LearnResult, _extract_pattern, get_learner, scan_and_learn,
)
from ahy_governance.self_healer import (
    RuleEngine, RecoveryLedgerEntry, IncidentType,
    RecoveryActionType, RecoveryStatus,
)


class FakeDB:
    enabled = True

    def __init__(self):
        self._entries = []
        self._rules = {}

    def recovery_ledger_list(self, workspace_id="", limit=500):
        return self._entries

    def recovery_rules_upsert(self, **kwargs):
        self._rules[kwargs["rule_id"]] = kwargs


def _make_entry(incident_type, error_message, recovery_action,
                diagnosed_by="llm", success=1, confidence=0.9):
    return {
        "incident_type": incident_type,
        "error_message": error_message,
        "recovery_action": recovery_action,
        "diagnosed_by": diagnosed_by,
        "success": success,
        "confidence": confidence,
    }


class TestPatternExtraction:
    def test_single_message(self):
        p = _extract_pattern(["Connection timed out after 30 seconds"])
        assert "Connection" in p or "timed" in p

    def test_multiple_similar_messages(self):
        msgs = [
            "OOM: allocation 8GB failed",
            "Out of memory: heap 12GB allocation failed",
            "Memory exhausted: 16GB alloc failed",
        ]
        p = _extract_pattern(msgs)
        assert "allocation" in p or "memory" in p

    def test_empty_returns_wildcard(self):
        assert _extract_pattern([]) == r".*"


class TestRecoveryLearner:
    def test_no_entries_returns_empty(self):
        db = FakeDB()
        learner = RecoveryLearner()
        learner.set_database(db)
        result = learner.scan_and_learn()
        assert result.scanned_entries == 0
        assert len(result.new_rules) == 0

    def test_insufficient_occurrences_skipped(self):
        db = FakeDB()
        db._entries = [
            _make_entry("timeout", "timeout", "retry"),
            _make_entry("timeout", "timeout again", "retry"),
        ]
        learner = RecoveryLearner(min_occurrences=3)
        learner.set_database(db)
        result = learner.scan_and_learn()
        assert result.skipped == 1
        assert len(result.new_rules) == 0

    def test_sufficient_cluster_generates_rule(self):
        db = FakeDB()
        for i in range(4):
            db._entries.append(
                _make_entry("memory_exhausted",
                           f"OOM: allocation {8+i}GB failed",
                           "restart_agent",
                           confidence=0.85 + i * 0.03),
            )
        engine = RuleEngine()
        learner = RecoveryLearner(min_occurrences=3, min_confidence=0.7)
        learner.set_database(db)
        learner.set_rule_engine(engine)
        result = learner.scan_and_learn()
        assert result.scanned_entries == 4
        assert result.clusters_found == 1
        assert len(result.new_rules) == 1
        rule = result.new_rules[0]
        assert rule.incident_type == IncidentType.MEMORY_EXHAUSTED
        assert rule.recovery_action_type == RecoveryActionType.RESTART_AGENT
        assert db._rules[rule.id]["enabled"] is False
        assert "[学习]" in rule.name
        assert "×4" in rule.name

    def test_auto_enable_learned_rules_is_explicit(self):
        db = FakeDB()
        for i in range(3):
            db._entries.append(
                _make_entry("rate_limit", f"429 rate limit {i}", "circuit_break"),
            )
        engine = RuleEngine()
        learner = RecoveryLearner(min_occurrences=3, auto_enable_learned_rules=True)
        learner.set_database(db)
        learner.set_rule_engine(engine)
        result = learner.scan_and_learn()
        rule = result.new_rules[0]
        assert db._rules[rule.id]["enabled"] is True
        assert any(r.id == rule.id for r in engine.rules)

    def test_existing_rule_skipped(self):
        db = FakeDB()
        for i in range(3):
            db._entries.append(
                _make_entry("timeout", f"timeout {i}", "retry"),
            )
        engine = RuleEngine()
        from ahy_governance.recovery_rules import default_recovery_rules
        engine.load_rules(default_recovery_rules())
        learner = RecoveryLearner(min_occurrences=3)
        learner.set_database(db)
        learner.set_rule_engine(engine)
        result = learner.scan_and_learn()
        # The default timeout-retry rule already exists → skipped
        assert result.skipped >= 1

    def test_low_confidence_entries_filtered(self):
        db = FakeDB()
        for i in range(5):
            db._entries.append(
                _make_entry("timeout", f"timeout {i}", "retry", confidence=0.3),
            )
        learner = RecoveryLearner(min_occurrences=3, min_confidence=0.7)
        learner.set_database(db)
        result = learner.scan_and_learn()
        assert len(result.new_rules) == 0

    def test_non_llm_diagnoses_filtered(self):
        db = FakeDB()
        for i in range(3):
            db._entries.append(
                _make_entry("timeout", f"timeout {i}", "retry",
                           diagnosed_by="rule"),
            )
        learner = RecoveryLearner(min_occurrences=3)
        learner.set_database(db)
        result = learner.scan_and_learn()
        assert len(result.new_rules) == 0

    def test_multiple_clusters(self):
        db = FakeDB()
        for i in range(3):
            db._entries.append(
                _make_entry("memory_exhausted", f"OOM {i}", "restart_agent"),
            )
        for i in range(3):
            db._entries.append(
                _make_entry("rate_limit", f"429 rate limit {i}", "circuit_break"),
            )
        learner = RecoveryLearner(min_occurrences=3)
        learner.set_database(db)
        result = learner.scan_and_learn()
        assert len(result.new_rules) == 2

    def test_learn_result_to_dict(self):
        r = LearnResult(
            new_rules=[], scanned_entries=10, clusters_found=3,
            skipped=2, detail="test",
        )
        d = r.to_dict()
        assert d["scanned_entries"] == 10
        assert d["clusters_found"] == 3
        assert d["skipped"] == 2

    def test_singleton(self):
        l1 = get_learner()
        l2 = get_learner()
        assert l1 is l2
