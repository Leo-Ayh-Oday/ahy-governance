"""Tests for ahy_governance.policy_engine — rules, conditions, evaluation."""

import pytest
from ahy_governance.policy_engine import (
    MatchCondition, PolicyRule, PolicyEngine,
    TriggerType, ActionType, RuleStatus,
    default_rules, get_policy_engine,
    _utc_now, _utc_ts, _parse_ts,
)


# ── Helpers ─────────────────────────────────────────────────

class TestHelpers:
    def test_utc_now(self):
        ts = _utc_now()
        assert isinstance(ts, str)
        assert "T" in ts

    def test_utc_ts(self):
        ts = _utc_ts()
        assert isinstance(ts, float)
        assert ts > 0

    def test_parse_ts_valid(self):
        ts = _parse_ts("2026-01-01T00:00:00")
        assert isinstance(ts, float)
        assert ts > 0

    def test_parse_ts_invalid(self):
        assert _parse_ts("not-a-date") == 0.0
        assert _parse_ts(None) == 0.0


# ── MatchCondition ──────────────────────────────────────────

class TestMatchCondition:
    def test_gt(self):
        c = MatchCondition(field="cost", operator="gt", value=10)
        assert c.evaluate({"cost": 15}) is True
        assert c.evaluate({"cost": 5}) is False
        assert c.evaluate({"cost": 10}) is False

    def test_lt(self):
        c = MatchCondition(field="rate", operator="lt", value=0.5)
        assert c.evaluate({"rate": 0.3}) is True
        assert c.evaluate({"rate": 0.7}) is False

    def test_eq(self):
        c = MatchCondition(field="severity", operator="eq", value="CRITICAL")
        assert c.evaluate({"severity": "critical"}) is True
        assert c.evaluate({"severity": "HIGH"}) is False

    def test_gte(self):
        c = MatchCondition(field="pct", operator="gte", value=80)
        assert c.evaluate({"pct": 80}) is True
        assert c.evaluate({"pct": 79}) is False

    def test_lte(self):
        c = MatchCondition(field="pct", operator="lte", value=50)
        assert c.evaluate({"pct": 50}) is True
        assert c.evaluate({"pct": 51}) is False

    def test_contains(self):
        c = MatchCondition(field="msg", operator="contains", value="error")
        assert c.evaluate({"msg": "An error occurred"}) is True
        assert c.evaluate({"msg": "All good"}) is False

    def test_missing_field(self):
        c = MatchCondition(field="missing", operator="gt", value=0)
        assert c.evaluate({}) is False

    def test_invalid_value_types(self):
        c = MatchCondition(field="x", operator="gt", value="not_a_number")
        assert c.evaluate({"x": 10}) is False

    def test_unknown_operator(self):
        c = MatchCondition(field="x", operator="unknown_op", value=10)
        assert c.evaluate({"x": 10}) is False


# ── PolicyRule ──────────────────────────────────────────────

class TestPolicyRule:
    def test_basic_match(self):
        rule = PolicyRule(
            id="r1", name="test", description="",
            trigger=TriggerType.COST_SPIKE,
            match_conditions=[MatchCondition(field="cost", operator="gt", value=5)],
            actions=[ActionType.ALERT],
        )
        actions = rule.evaluate(TriggerType.COST_SPIKE, {"cost": 10})
        assert actions == [ActionType.ALERT]

    def test_wrong_trigger(self):
        rule = PolicyRule(
            id="r1", name="test", description="",
            trigger=TriggerType.COST_SPIKE,
            match_conditions=[MatchCondition(field="cost", operator="gt", value=5)],
            actions=[ActionType.ALERT],
        )
        actions = rule.evaluate(TriggerType.AGENT_OFFLINE, {"cost": 10})
        assert actions == []

    def test_disabled_rule(self):
        rule = PolicyRule(
            id="r1", name="test", description="",
            trigger=TriggerType.COST_SPIKE,
            actions=[ActionType.ALERT],
            enabled=False,
        )
        actions = rule.evaluate(TriggerType.COST_SPIKE, {})
        assert actions == []

    def test_condition_not_met(self):
        rule = PolicyRule(
            id="r1", name="test", description="",
            trigger=TriggerType.COST_SPIKE,
            match_conditions=[MatchCondition(field="cost", operator="gt", value=100)],
            actions=[ActionType.ALERT],
        )
        actions = rule.evaluate(TriggerType.COST_SPIKE, {"cost": 50})
        assert actions == []

    def test_cooldown(self):
        rule = PolicyRule(
            id="r1", name="test", description="",
            trigger=TriggerType.COST_SPIKE,
            actions=[ActionType.ALERT],
            cooldown_seconds=300,
        )
        # First trigger
        actions1 = rule.evaluate(TriggerType.COST_SPIKE, {})
        assert actions1 == [ActionType.ALERT]
        # Second trigger within cooldown
        actions2 = rule.evaluate(TriggerType.COST_SPIKE, {})
        assert actions2 == []

    def test_no_conditions(self):
        rule = PolicyRule(
            id="r1", name="test", description="",
            trigger=TriggerType.AGENT_OFFLINE,
            match_conditions=[],
            actions=[ActionType.ALERT],
        )
        actions = rule.evaluate(TriggerType.AGENT_OFFLINE, {})
        assert actions == [ActionType.ALERT]

    def test_deduplicate_actions(self):
        rule = PolicyRule(
            id="r1", name="test", description="",
            trigger=TriggerType.COST_SPIKE,
            actions=[ActionType.ALERT, ActionType.ALERT, ActionType.BLOCK],
        )
        actions = rule.evaluate(TriggerType.COST_SPIKE, {})
        assert actions == [ActionType.ALERT, ActionType.BLOCK]

    def test_to_dict(self):
        rule = PolicyRule(
            id="r1", name="test", description="desc",
            trigger=TriggerType.COST_SPIKE,
            match_conditions=[MatchCondition(field="cost", operator="gt", value=5)],
            actions=[ActionType.ALERT],
        )
        d = rule.to_dict()
        assert d["id"] == "r1"
        assert d["name"] == "test"
        assert d["trigger"] == "cost_spike"
        assert len(d["match"]) == 1
        assert d["actions"] == ["alert"]

    def test_from_dict(self):
        d = {
            "id": "r1", "name": "test", "description": "desc",
            "trigger": "cost_spike",
            "match": [{"field": "cost", "operator": "gt", "value": 5}],
            "actions": ["alert"],
            "enabled": True,
            "cooldown_seconds": 100,
        }
        rule = PolicyRule.from_dict(d)
        assert rule.id == "r1"
        assert rule.trigger == TriggerType.COST_SPIKE
        assert len(rule.match_conditions) == 1

    def test_from_dict_invalid(self):
        rule = PolicyRule.from_dict({"id": "bad", "trigger": "nonexistent_trigger"})
        assert rule.id == "invalid"
        assert rule.enabled is False

    def test_from_dict_missing_fields(self):
        rule = PolicyRule.from_dict({})
        # Empty dict uses defaults: id="" trigger=cost_spike
        assert rule.trigger == TriggerType.COST_SPIKE


# ── PolicyEngine ────────────────────────────────────────────

class TestPolicyEngine:
    def test_evaluate_no_rules(self):
        engine = PolicyEngine()
        actions = engine.evaluate(TriggerType.COST_SPIKE, {"cost": 100})
        assert actions == []

    def test_evaluate_matching_rule(self):
        engine = PolicyEngine()
        rule = PolicyRule(
            id="r1", name="test", description="",
            trigger=TriggerType.COST_SPIKE,
            match_conditions=[MatchCondition(field="cost", operator="gt", value=50)],
            actions=[ActionType.BLOCK],
        )
        engine.load_rules([rule])
        actions = engine.evaluate(TriggerType.COST_SPIKE, {"cost": 100})
        assert ActionType.BLOCK in actions

    def test_register_handler(self):
        engine = PolicyEngine()
        calls = []
        engine.register_handler(ActionType.ALERT, lambda rule, ctx: calls.append(ctx))
        rule = PolicyRule(
            id="r1", name="test", description="",
            trigger=TriggerType.COST_SPIKE,
            actions=[ActionType.ALERT],
        )
        engine.load_rules([rule])
        engine.evaluate(TriggerType.COST_SPIKE, {"cost": 100})
        assert len(calls) == 1

    def test_handler_exception_logged(self):
        engine = PolicyEngine()
        def bad_handler(rule, ctx):
            raise RuntimeError("boom")
        engine.register_handler(ActionType.ALERT, bad_handler)
        rule = PolicyRule(
            id="r1", name="test", description="",
            trigger=TriggerType.COST_SPIKE,
            actions=[ActionType.ALERT],
        )
        engine.load_rules([rule])
        # Should not raise
        actions = engine.evaluate(TriggerType.COST_SPIKE, {})
        assert actions == [ActionType.ALERT]

    def test_rules_property(self):
        engine = PolicyEngine()
        assert engine.rules == []
        rule = PolicyRule(id="r1", name="t", description="", trigger=TriggerType.COST_SPIKE)
        engine.load_rules([rule])
        assert len(engine.rules) == 1

    def test_rule_by_id(self):
        engine = PolicyEngine()
        rule = PolicyRule(id="findme", name="t", description="", trigger=TriggerType.COST_SPIKE)
        engine.load_rules([rule])
        assert engine.rule_by_id("findme") is rule
        assert engine.rule_by_id("nope") is None


# ── Default rules ───────────────────────────────────────────

class TestDefaultRules:
    def test_returns_list(self):
        rules = default_rules()
        assert isinstance(rules, list)
        assert len(rules) >= 5

    def test_all_rules_have_ids(self):
        for rule in default_rules():
            assert rule.id
            assert rule.name

    def test_default_rule_types(self):
        rules = default_rules()
        triggers = {r.trigger for r in rules}
        assert TriggerType.COST_SPIKE in triggers
        assert TriggerType.BUDGET_WARNING in triggers
        assert TriggerType.CONFLICT_DETECTED in triggers
        assert TriggerType.AGENT_OFFLINE in triggers
        assert TriggerType.PROMPT_INJECTION in triggers


# ── Singleton ───────────────────────────────────────────────

class TestSingleton:
    def test_get_policy_engine(self):
        import ahy_governance.policy_engine as pe_mod
        pe_mod._engine = None
        engine = get_policy_engine()
        assert isinstance(engine, PolicyEngine)
        assert len(engine.rules) >= 5
        pe_mod._engine = None


# ── Enums ───────────────────────────────────────────────────

class TestEnums:
    def test_trigger_types(self):
        assert TriggerType.COST_SPIKE.value == "cost_spike"
        assert TriggerType.BUDGET_WARNING.value == "budget_warning"

    def test_action_types(self):
        assert ActionType.ALERT.value == "alert"
        assert ActionType.BLOCK.value == "block"
        assert ActionType.LOG.value == "log"
        assert ActionType.THROTTLE.value == "throttle"

    def test_rule_status(self):
        assert RuleStatus.ACTIVE.value == "active"
        assert RuleStatus.INACTIVE.value == "inactive"
        assert RuleStatus.TRIGGERED.value == "triggered"
