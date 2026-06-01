"""Tests for Recovery Rules — 自愈规则库."""

from ahy_governance.recovery_rules import default_recovery_rules
from ahy_governance.self_healer import IncidentType, RecoveryActionType, RuleEngine


class TestDefaultRules:
    def test_returns_10_rules(self):
        rules = default_recovery_rules()
        assert len(rules) == 10

    def test_all_rules_have_unique_ids(self):
        rules = default_recovery_rules()
        ids = [r.id for r in rules]
        assert len(ids) == len(set(ids))

    def test_all_rules_have_names(self):
        for r in default_recovery_rules():
            assert r.name

    def test_all_rules_have_valid_incident_types(self):
        for r in default_recovery_rules():
            assert isinstance(r.incident_type, IncidentType)

    def test_all_rules_have_valid_action_types(self):
        for r in default_recovery_rules():
            assert isinstance(r.recovery_action_type, RecoveryActionType)

    def test_rules_are_sorted_by_priority(self):
        rules = default_recovery_rules()
        engine = RuleEngine()
        engine.load_rules(rules)
        priorities = [r.priority for r in engine.rules]
        assert priorities == sorted(priorities)


class TestPatternMatching:
    def test_timeout_rule_matches(self):
        rules = default_recovery_rules()
        engine = RuleEngine()
        engine.load_rules(rules)
        # Should match the timeout rule (not the unknown catch-all)
        match = engine.match(IncidentType.TIMEOUT, "Request timed out after 30s")
        assert match is not None
        assert match.id == "timeout-retry"

    def test_auth_rule_matches(self):
        rules = default_recovery_rules()
        engine = RuleEngine()
        engine.load_rules(rules)
        match = engine.match(IncidentType.AUTH_ERROR, "401 Unauthorized - invalid API key")
        assert match is not None
        assert match.id == "auth-escalate-human"

    def test_rate_limit_rule_matches(self):
        rules = default_recovery_rules()
        engine = RuleEngine()
        engine.load_rules(rules)
        match = engine.match(IncidentType.RATE_LIMIT, "429 Too Many Requests")
        assert match is not None
        assert match.id == "rate-limit-backoff"

    def test_unknown_catchall_matches_anything(self):
        rules = default_recovery_rules()
        engine = RuleEngine()
        engine.load_rules(rules)
        match = engine.match(IncidentType.UNKNOWN, "completely unexpected error XYZ123")
        assert match is not None
        assert match.id == "unknown-escalate"

    def test_cooldown_prevents_double_match(self):
        rules = default_recovery_rules()
        engine = RuleEngine()
        engine.load_rules(rules)
        match1 = engine.match(IncidentType.TIMEOUT, "timeout error")
        assert match1 is not None
        assert match1.id == "timeout-retry"
        # Second match blocked by cooldown but caught by UNKNOWN catch-all
        match2 = engine.match(IncidentType.TIMEOUT, "another timeout")
        assert match2 is not None
        assert match2.id != "timeout-retry"  # cooldown prevented re-trigger
