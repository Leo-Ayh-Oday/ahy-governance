"""Tests for ahy_governance.policy_engine — rules, conditions, evaluation."""

import pytest
from ahy_governance.policy_engine import (
    MatchCondition, PolicyRule, PolicyEngine,
    TriggerType, ActionType, RuleStatus,
    default_rules, get_policy_engine,
    _utc_now, _utc_ts, _parse_ts,
    AgentLevel, RiskClass, AgentCapabilities, GovernanceStrategy,
    evaluate_agent_level, recommend_strategy, AGENT_LEVEL_STRATEGIES,
    level_policy_rules,
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


# ── Agent Level Grading ──────────────────────────────────────

class TestAgentLevel:
    def test_level_values(self):
        assert AgentLevel.LEVEL_0.value == 0
        assert AgentLevel.LEVEL_5.value == 5

    def test_all_levels_exist(self):
        assert len(AgentLevel) == 6  # 0-5


class TestRiskClass:
    def test_read_only(self):
        assert RiskClass.READ_ONLY.value == "read_only"

    def test_all_risk_classes(self):
        assert len(RiskClass) == 15

    def test_critical_classes_exist(self):
        assert RiskClass.DESTRUCTIVE.value == "destructive"
        assert RiskClass.PRIVILEGED_ADMIN.value == "privileged_admin"
        assert RiskClass.FINANCIAL.value == "financial"


class TestAgentCapabilities:
    def test_defaults(self):
        caps = AgentCapabilities()
        assert caps.can_read is False
        assert caps.requires_approval is True
        assert caps.max_tool_risk == RiskClass.READ_ONLY

    def test_to_dict(self):
        caps = AgentCapabilities(can_read=True, can_search=True)
        d = caps.to_dict()
        assert d["can_read"] is True
        assert d["can_search"] is True
        assert d["max_tool_risk"] == "read_only"

    def test_from_dict(self):
        d = {
            "can_read": True,
            "can_draft": True,
            "requires_approval": False,
            "max_tool_risk": "write_local",
        }
        caps = AgentCapabilities.from_dict(d)
        assert caps.can_read is True
        assert caps.can_draft is True
        assert caps.requires_approval is False
        assert caps.max_tool_risk == RiskClass.WRITE_LOCAL

    def test_from_dict_invalid_risk(self):
        caps = AgentCapabilities.from_dict({"max_tool_risk": "nonexistent"})
        assert caps.max_tool_risk == RiskClass.READ_ONLY

    def test_from_dict_defaults(self):
        caps = AgentCapabilities.from_dict({})
        assert caps.can_read is False
        assert caps.requires_approval is True


class TestEvaluateAgentLevel:
    def test_level_0_no_capabilities(self):
        caps = AgentCapabilities()
        assert evaluate_agent_level(caps) == AgentLevel.LEVEL_0

    def test_level_1_read_only(self):
        caps = AgentCapabilities(can_read=True)
        assert evaluate_agent_level(caps) == AgentLevel.LEVEL_1

    def test_level_1_search_only(self):
        caps = AgentCapabilities(can_search=True)
        assert evaluate_agent_level(caps) == AgentLevel.LEVEL_1

    def test_level_2_drafting(self):
        caps = AgentCapabilities(can_read=True, can_draft=True)
        assert evaluate_agent_level(caps) == AgentLevel.LEVEL_2

    def test_level_2_draft_needs_read_or_search(self):
        # can_draft alone without read/search → still level 0
        caps = AgentCapabilities(can_draft=True)
        assert evaluate_agent_level(caps) == AgentLevel.LEVEL_0

    def test_level_3_approval_gated(self):
        caps = AgentCapabilities(
            can_read=True, can_draft=True,
            can_write_local=True, requires_approval=True,
        )
        assert evaluate_agent_level(caps) == AgentLevel.LEVEL_3

    def test_level_3_needs_approval(self):
        # can_write_local but no approval → not level 3
        caps = AgentCapabilities(
            can_read=True, can_write_local=True, requires_approval=False,
        )
        # Without approval and without budget controls, this would be level 1
        # (can_read=True, but no can_draft so doesn't hit level 2)
        assert evaluate_agent_level(caps) == AgentLevel.LEVEL_1

    def test_level_4_autonomous(self):
        caps = AgentCapabilities(
            can_read=True, can_draft=True,
            can_write_local=True, can_write_external=True,
            requires_approval=False, has_budget_controls=True,
        )
        assert evaluate_agent_level(caps) == AgentLevel.LEVEL_4

    def test_level_4_needs_no_approval_and_budget(self):
        # can_write_external but requires_approval → not level 4
        caps = AgentCapabilities(
            can_read=True, can_draft=True,
            can_write_local=True, can_write_external=True,
            requires_approval=True, has_budget_controls=True,
        )
        assert evaluate_agent_level(caps) == AgentLevel.LEVEL_3

    def test_level_5_full_autonomous(self):
        caps = AgentCapabilities(
            can_read=True, can_draft=True,
            can_write_local=True, can_write_external=True,
            can_execute_code=True,
            requires_approval=False, has_budget_controls=True,
            has_durable_state=True, has_checkpoint_recovery=True,
        )
        assert evaluate_agent_level(caps) == AgentLevel.LEVEL_5

    def test_level_5_needs_all_conditions(self):
        # Missing checkpoint_recovery → falls to level 4
        caps = AgentCapabilities(
            can_read=True, can_draft=True,
            can_write_external=True, can_execute_code=True,
            requires_approval=False, has_budget_controls=True,
            has_durable_state=True, has_checkpoint_recovery=False,
        )
        assert evaluate_agent_level(caps) == AgentLevel.LEVEL_4


class TestGovernanceStrategy:
    def test_all_levels_have_strategies(self):
        for level in AgentLevel:
            assert level in AGENT_LEVEL_STRATEGIES

    def test_level_0_minimal(self):
        s = AGENT_LEVEL_STRATEGIES[AgentLevel.LEVEL_0]
        assert s.label == "Answer-Only"
        assert s.needs_conflict_detection is False
        assert s.needs_rbac is False
        assert s.needs_audit is True

    def test_level_1_cost_tracking(self):
        s = AGENT_LEVEL_STRATEGIES[AgentLevel.LEVEL_1]
        assert s.needs_cost_tracking is True
        assert s.needs_conflict_detection is False

    def test_level_2_prompt_guard(self):
        s = AGENT_LEVEL_STRATEGIES[AgentLevel.LEVEL_2]
        assert s.needs_prompt_guard is True
        assert RiskClass.DRAFT_ONLY in s.risk_classes_allowed

    def test_level_3_full_governance(self):
        s = AGENT_LEVEL_STRATEGIES[AgentLevel.LEVEL_3]
        assert s.needs_conflict_detection is True
        assert s.needs_rbac is True
        assert s.needs_human_fallback is True

    def test_level_4_anomaly_detection(self):
        s = AGENT_LEVEL_STRATEGIES[AgentLevel.LEVEL_4]
        assert s.needs_anomaly_detection is True
        assert s.needs_auto_resolution is True
        assert s.needs_circuit_breaker is True

    def test_level_5_all_controls(self):
        s = AGENT_LEVEL_STRATEGIES[AgentLevel.LEVEL_5]
        assert s.needs_conflict_detection is True
        assert s.needs_anomaly_detection is True
        assert s.needs_auto_resolution is True
        assert s.needs_prompt_guard is True
        assert s.needs_rbac is True
        assert s.needs_circuit_breaker is True
        assert s.needs_realtime_alerts is True
        assert s.needs_human_fallback is True
        assert len(s.risk_classes_allowed) == 15  # all risk classes

    def test_to_dict(self):
        s = AGENT_LEVEL_STRATEGIES[AgentLevel.LEVEL_3]
        d = s.to_dict()
        assert d["level"] == 3
        assert d["needs_conflict_detection"] is True
        assert isinstance(d["risk_classes_allowed"], list)


class TestRecommendStrategy:
    def test_returns_correct_strategy(self):
        s = recommend_strategy(AgentLevel.LEVEL_4)
        assert s.level == AgentLevel.LEVEL_4
        assert s.needs_anomaly_detection is True

    def test_all_levels_work(self):
        for level in AgentLevel:
            s = recommend_strategy(level)
            assert s.level == level


class TestLevelPolicyRules:
    def test_returns_rules(self):
        rules = level_policy_rules()
        assert len(rules) >= 5

    def test_rules_use_level_trigger(self):
        rules = level_policy_rules()
        for r in rules:
            assert r.trigger == TriggerType.AGENT_LEVEL_EVALUATED

    def test_conflict_detection_rule(self):
        rules = level_policy_rules()
        rule = next(r for r in rules if r.id == "level-3-plus-conflict-detection")
        assert ActionType.ALERT in rule.actions
        assert ActionType.LOG in rule.actions

    def test_circuit_breaker_rule_blocks(self):
        rules = level_policy_rules()
        rule = next(r for r in rules if r.id == "level-5-circuit-breaker")
        assert ActionType.BLOCK in rule.actions

    def test_default_rules_include_level_rules(self):
        rules = default_rules()
        level_ids = {r.id for r in rules}
        assert "level-3-plus-conflict-detection" in level_ids
        assert "level-5-circuit-breaker" in level_ids


class TestLevelRuleEvaluation:
    """Test that level-based policy rules fire correctly."""

    def test_level_3_no_conflict_detection_triggers_alert(self):
        engine = PolicyEngine()
        engine.load_rules(level_policy_rules())
        actions = engine.evaluate(
            TriggerType.AGENT_LEVEL_EVALUATED,
            {"agent_level": 3, "has_conflict_detection": False},
        )
        assert ActionType.ALERT in actions
        assert ActionType.LOG in actions

    def test_level_2_no_conflict_detection_no_trigger(self):
        engine = PolicyEngine()
        engine.load_rules(level_policy_rules())
        actions = engine.evaluate(
            TriggerType.AGENT_LEVEL_EVALUATED,
            {"agent_level": 2, "has_conflict_detection": False},
        )
        assert actions == []

    def test_level_5_no_circuit_breaker_blocked(self):
        engine = PolicyEngine()
        engine.load_rules(level_policy_rules())
        actions = engine.evaluate(
            TriggerType.AGENT_LEVEL_EVALUATED,
            {"agent_level": 5, "has_circuit_breaker": False},
        )
        assert ActionType.BLOCK in actions

    def test_level_4_no_budget_blocked(self):
        engine = PolicyEngine()
        engine.load_rules(level_policy_rules())
        actions = engine.evaluate(
            TriggerType.AGENT_LEVEL_EVALUATED,
            {"agent_level": 4, "has_budget_controls": False},
        )
        assert ActionType.BLOCK in actions

    def test_unapproved_external_write_blocked(self):
        engine = PolicyEngine()
        engine.load_rules(level_policy_rules())
        actions = engine.evaluate(
            TriggerType.AGENT_LEVEL_EVALUATED,
            {
                "agent_level": 3,
                "can_write_external": True,
                "requires_approval": False,
            },
        )
        assert ActionType.BLOCK in actions
