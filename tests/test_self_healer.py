"""Tests for Self Healer — Agent 自愈引擎."""

from __future__ import annotations

import time
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from ahy_governance.self_healer import (
    SelfHealer,
    SelfHealLevel,
    RecoveryActionType,
    IncidentType,
    RecoveryAction,
    RecoveryRule,
    RecoveryLedgerEntry,
    RecoveryStatus,
    HealResult,
    RuleEngine,
    LLMDoctor,
    RecoveryLedger,
    get_healer,
    self_heal,
)
from ahy_governance.recovery_rules import default_recovery_rules


# ── Helper: Fake DB for RecoveryLedger ────────────────────────

class FakeDB:
    enabled = True

    def __init__(self):
        self._entries = []

    def recovery_ledger_insert(self, **kwargs) -> int:
        self._entries.append(kwargs)
        return len(self._entries)

    def recovery_ledger_similar(self, incident_type, error_message, workspace_id, limit):
        return [
            e for e in self._entries[-limit:]
            if e["incident_type"] == incident_type
        ]

    def recovery_ledger_list(self, agent_name, incident_type, workspace_id, limit):
        return self._entries[-limit:]


# ── Enums ─────────────────────────────────────────────────────

class TestEnums:
    def test_self_heal_levels(self):
        assert SelfHealLevel.RULE_ONLY.value == "rule_only"
        assert SelfHealLevel.LLM_ASSISTED.value == "llm_assisted"
        assert SelfHealLevel.FULL_AUTO.value == "full_auto"

    def test_recovery_action_types(self):
        assert len(RecoveryActionType) == 8

    def test_incident_types(self):
        assert len(IncidentType) == 10

    def test_recovery_statuses(self):
        assert RecoveryStatus.ATTEMPTED.value == "attempted"
        assert RecoveryStatus.SUCCEEDED.value == "succeeded"
        assert RecoveryStatus.FAILED.value == "failed"
        assert RecoveryStatus.ESCALATED.value == "escalated"


# ── Data Classes ──────────────────────────────────────────────

class TestRecoveryAction:
    def test_to_dict(self):
        a = RecoveryAction(
            action_type=RecoveryActionType.RETRY,
            description="Retry with backoff",
            params={"max": 3},
            confidence=0.9,
            source="rule",
        )
        d = a.to_dict()
        assert d["action_type"] == "retry"
        assert d["description"] == "Retry with backoff"
        assert d["confidence"] == 0.9
        assert d["source"] == "rule"


class TestRecoveryRule:
    def test_match_by_type_and_pattern(self):
        rule = RecoveryRule(
            id="test", name="Test", incident_type=IncidentType.TIMEOUT,
            pattern=r"(?i)timeout", recovery_action_type=RecoveryActionType.RETRY,
        )
        assert rule.match(IncidentType.TIMEOUT, "Connection timeout occurred")
        assert not rule.match(IncidentType.TIMEOUT, "Everything is fine")
        assert not rule.match(IncidentType.AUTH_ERROR, "Connection timeout")

    def test_disabled_rule_does_not_match(self):
        rule = RecoveryRule(
            id="test", name="Test", incident_type=IncidentType.TIMEOUT,
            pattern=r"timeout", recovery_action_type=RecoveryActionType.RETRY,
            enabled=False,
        )
        assert not rule.match(IncidentType.TIMEOUT, "timeout")

    def test_unknown_type_matches_all(self):
        rule = RecoveryRule(
            id="catchall", name="Catch", incident_type=IncidentType.UNKNOWN,
            pattern=r".*", recovery_action_type=RecoveryActionType.ALERT_HUMAN,
        )
        assert rule.match(IncidentType.TIMEOUT, "timeout")
        assert rule.match(IncidentType.AUTH_ERROR, "401")

    def test_cooldown_respected(self):
        engine = RuleEngine()
        rule = RecoveryRule(
            id="test", name="Test", incident_type=IncidentType.TIMEOUT,
            pattern=r"timeout", recovery_action_type=RecoveryActionType.RETRY,
            cooldown_seconds=60,
        )
        engine.load_rules([rule])
        assert engine.match(IncidentType.TIMEOUT, "timeout") is not None
        assert engine.match(IncidentType.TIMEOUT, "timeout again") is None

    def test_to_dict(self):
        rule = RecoveryRule(
            id="r1", name="Test", incident_type=IncidentType.TIMEOUT,
            pattern=r"timeout", recovery_action_type=RecoveryActionType.RETRY,
            priority=10, cooldown_seconds=60,
        )
        d = rule.to_dict()
        assert d["id"] == "r1"
        assert d["incident_type"] == "timeout"
        assert d["action"] == "retry"


class TestHealResult:
    def test_to_dict_no_action(self):
        r = HealResult(
            agent_name="A", incident_type=IncidentType.UNKNOWN,
            status=RecoveryStatus.ESCALATED, diagnosed_by="system",
        )
        d = r.to_dict()
        assert d["agent_name"] == "A"
        assert d["action"] is None
        assert d["status"] == "escalated"

    def test_to_dict_with_action(self):
        action = RecoveryAction(
            action_type=RecoveryActionType.RETRY, description="Retry",
        )
        r = HealResult(
            agent_name="B", incident_type=IncidentType.TIMEOUT,
            action=action, status=RecoveryStatus.ATTEMPTED, diagnosed_by="rule",
        )
        d = r.to_dict()
        assert d["action"]["action_type"] == "retry"

    def test_restore_context_serialized(self):
        r = HealResult(
            agent_name="B", incident_type=IncidentType.TIMEOUT,
            status=RecoveryStatus.ATTEMPTED,
            restore_context={"session_id": "s1", "state": {"step": 47}},
        )
        d = r.to_dict()
        assert d["restore_context"]["session_id"] == "s1"
        assert d["restore_context"]["state"]["step"] == 47


# ── Rule Engine ───────────────────────────────────────────────

class TestRuleEngine:
    def test_load_and_match(self):
        engine = RuleEngine()
        rules = [
            RecoveryRule(
                id="r1", name="R1", incident_type=IncidentType.TIMEOUT,
                pattern=r"timeout", recovery_action_type=RecoveryActionType.RETRY,
                priority=50,
            ),
            RecoveryRule(
                id="r2", name="R2", incident_type=IncidentType.AUTH_ERROR,
                pattern=r"401", recovery_action_type=RecoveryActionType.ALERT_HUMAN,
                priority=10,
            ),
        ]
        engine.load_rules(rules)
        # Higher priority (lower number) should match first
        match = engine.match(IncidentType.AUTH_ERROR, "401 Unauthorized")
        assert match is not None
        assert match.id == "r2"

    def test_no_match_returns_none(self):
        engine = RuleEngine()
        engine.load_rules([
            RecoveryRule(
                id="r1", name="R1", incident_type=IncidentType.TIMEOUT,
                pattern=r"timeout", recovery_action_type=RecoveryActionType.RETRY,
            ),
        ])
        assert engine.match(IncidentType.TIMEOUT, "everything ok") is None

    def test_rules_property(self):
        engine = RuleEngine()
        engine.load_rules([
            RecoveryRule(
                id="r1", name="R1", incident_type=IncidentType.TIMEOUT,
                pattern=r"timeout", recovery_action_type=RecoveryActionType.RETRY,
                priority=20,
            ),
            RecoveryRule(
                id="r2", name="R2", incident_type=IncidentType.AUTH_ERROR,
                pattern=r"401", recovery_action_type=RecoveryActionType.ALERT_HUMAN,
                priority=10,
            ),
        ])
        assert len(engine.rules) == 2
        assert engine.rules[0].id == "r2"  # sorted by priority


# ── LLM Doctor ────────────────────────────────────────────────

class TestLLMDoctor:
    def test_no_fn_returns_none(self):
        doctor = LLMDoctor()
        result = doctor.diagnose("A", IncidentType.TIMEOUT, "timed out", {})
        assert result is None

    def test_with_fn_returns_action(self):
        doctor = LLMDoctor()
        doctor.set_diagnose_fn(lambda err, ctx: RecoveryAction(
            action_type=RecoveryActionType.RETRY,
            description=f"LLM diagnosed: {err[:20]}",
            source="llm",
            confidence=0.8,
        ))
        result = doctor.diagnose("A", IncidentType.TIMEOUT, "Connection timed out", {})
        assert result is not None
        assert result.action_type == RecoveryActionType.RETRY
        assert result.source == "llm"

    def test_fn_exception_returns_none(self):
        doctor = LLMDoctor()
        doctor.set_diagnose_fn(lambda err, ctx: 1 / 0)
        result = doctor.diagnose("A", IncidentType.TIMEOUT, "err", {})
        assert result is None


# ── Recovery Ledger ───────────────────────────────────────────

class TestRecoveryLedger:
    def test_record_returns_zero_without_db(self):
        ledger = RecoveryLedger()
        entry = RecoveryLedgerEntry(agent_name="A")
        assert ledger.record(entry) == 0

    def test_record_with_db(self):
        db = FakeDB()
        ledger = RecoveryLedger()
        ledger.set_database(db)
        entry = RecoveryLedgerEntry(
            agent_name="Planner",
            incident_type=IncidentType.TIMEOUT,
            error_message="timed out",
            recovery_action=RecoveryActionType.RETRY,
            status=RecoveryStatus.ATTEMPTED,
        )
        rid = ledger.record(entry)
        assert rid > 0

    def test_find_similar(self):
        db = FakeDB()
        ledger = RecoveryLedger()
        ledger.set_database(db)
        # Record a successful recovery
        entry = RecoveryLedgerEntry(
            agent_name="Planner",
            incident_type=IncidentType.TIMEOUT,
            error_message="timed out",
            recovery_action=RecoveryActionType.RETRY,
            status=RecoveryStatus.SUCCEEDED,
            confidence=0.9,
        )
        ledger.record(entry)
        similar = ledger.find_similar(IncidentType.TIMEOUT, "timed out again")
        assert len(similar) > 0

    def test_query(self):
        db = FakeDB()
        ledger = RecoveryLedger()
        ledger.set_database(db)
        entry = RecoveryLedgerEntry(agent_name="X")
        ledger.record(entry)
        results = ledger.query(agent_name="X")
        assert len(results) > 0


# ── Self Healer: RULE_ONLY ─────────────────────────────────────

class TestSelfHealerRuleOnly:
    def test_rule_match_resolves(self):
        healer = SelfHealer(level=SelfHealLevel.RULE_ONLY)
        healer.load_rules(default_recovery_rules())
        result = healer.self_heal("Agent1", IncidentType.TIMEOUT,
                                  "Request timed out after 30s")
        assert result.status == RecoveryStatus.ATTEMPTED
        assert result.diagnosed_by == "rule"
        assert result.action.action_type == RecoveryActionType.RETRY

    def test_no_rule_escalates(self):
        healer = SelfHealer(level=SelfHealLevel.RULE_ONLY)
        healer.load_rules([])  # no rules loaded
        result = healer.self_heal("Agent1", IncidentType.TIMEOUT,
                                  "Request timed out")
        assert result.status == RecoveryStatus.ESCALATED
        assert result.diagnosed_by == "system"

    def test_llm_not_used_in_rule_only(self):
        healer = SelfHealer(level=SelfHealLevel.RULE_ONLY)
        healer.load_rules([])
        doctor = LLMDoctor()
        doctor.set_diagnose_fn(lambda err, ctx: RecoveryAction(
            action_type=RecoveryActionType.RETRY, description="LLM fix",
        ))
        healer.set_llm_doctor(doctor)
        result = healer.self_heal("A", IncidentType.TIMEOUT, "timeout")
        assert result.diagnosed_by == "system"  # escalated, not llm

    def test_rule_result_includes_checkpoint_restore_context(self):
        healer = SelfHealer(level=SelfHealLevel.RULE_ONLY)
        healer.load_rules(default_recovery_rules())
        result = healer.self_heal(
            "Agent1", IncidentType.TIMEOUT, "Request timed out after 30s",
            context={
                "checkpoint": {
                    "checkpoint_id": 7,
                    "agent_name": "Agent1",
                    "session_id": "s1",
                    "step": "step-47",
                    "created_at": "2026-06-02T00:00:00+00:00",
                    "state": {"goal": "continue", "step": 47},
                }
            },
        )
        assert result.restore_context == {
            "agent_name": "Agent1",
            "session_id": "s1",
            "checkpoint_id": 7,
            "step": "step-47",
            "created_at": "2026-06-02T00:00:00+00:00",
            "state": {"goal": "continue", "step": 47},
        }


# ── Self Healer: LLM_ASSISTED ──────────────────────────────────

class TestSelfHealerLLMAssisted:
    def test_llm_diagnosis_escalated(self):
        healer = SelfHealer(level=SelfHealLevel.LLM_ASSISTED)
        healer.load_rules([])
        doctor = LLMDoctor()
        doctor.set_diagnose_fn(lambda err, ctx: RecoveryAction(
            action_type=RecoveryActionType.MODEL_FALLBACK,
            description="Switch to Haiku",
            source="llm",
        ))
        healer.set_llm_doctor(doctor)
        result = healer.self_heal("A", IncidentType.HALLUCINATION, "hallucination detected")
        assert result.status == RecoveryStatus.ESCALATED
        assert result.diagnosed_by == "llm"

    def test_rule_still_wins(self):
        healer = SelfHealer(level=SelfHealLevel.LLM_ASSISTED)
        healer.load_rules(default_recovery_rules())
        result = healer.self_heal("A", IncidentType.TIMEOUT, "Connection timeout")
        assert result.diagnosed_by == "rule"  # rule beats llm


# ── Self Healer: FULL_AUTO ─────────────────────────────────────

class TestSelfHealerFullAuto:
    def test_llm_auto_applied(self):
        healer = SelfHealer(level=SelfHealLevel.FULL_AUTO)
        healer.load_rules([])
        doctor = LLMDoctor()
        doctor.set_diagnose_fn(lambda err, ctx: RecoveryAction(
            action_type=RecoveryActionType.MODEL_FALLBACK,
            description="Auto fix",
            source="llm",
        ))
        healer.set_llm_doctor(doctor)
        result = healer.self_heal("A", IncidentType.HALLUCINATION,
                                  "Agent hallucinated data")
        assert result.status == RecoveryStatus.ATTEMPTED
        assert result.diagnosed_by == "llm"

    def test_high_risk_llm_action_escalates(self):
        healer = SelfHealer(level=SelfHealLevel.FULL_AUTO)
        healer.load_rules([])
        doctor = LLMDoctor()
        doctor.set_diagnose_fn(lambda err, ctx: RecoveryAction(
            action_type=RecoveryActionType.RESTART_AGENT,
            description="Restart now",
            source="llm",
        ))
        healer.set_llm_doctor(doctor)
        result = healer.self_heal("A", IncidentType.MEMORY_EXHAUSTED, "OOM")
        assert result.status == RecoveryStatus.ESCALATED
        assert result.diagnosed_by == "policy"
        assert result.action.action_type == RecoveryActionType.ALERT_HUMAN
        assert result.action.params["blocked_action"] == "restart_agent"

    def test_auth_error_llm_action_escalates(self):
        healer = SelfHealer(level=SelfHealLevel.FULL_AUTO)
        healer.load_rules([])
        doctor = LLMDoctor()
        doctor.set_diagnose_fn(lambda err, ctx: RecoveryAction(
            action_type=RecoveryActionType.RETRY,
            description="Retry auth",
            source="llm",
        ))
        healer.set_llm_doctor(doctor)
        result = healer.self_heal("A", IncidentType.AUTH_ERROR, "401")
        assert result.status == RecoveryStatus.ESCALATED
        assert result.diagnosed_by == "policy"
        assert result.action.action_type == RecoveryActionType.ALERT_HUMAN


# ── Self Healer: Escalation ────────────────────────────────────

class TestSelfHealerEscalation:
    def test_escalation_handler_called(self):
        healer = SelfHealer(level=SelfHealLevel.RULE_ONLY)
        healer.load_rules([])
        called = []

        def handler(agent, itype, msg, ctx):
            called.append((agent, itype, msg))

        healer.set_escalation_handler(handler)
        result = healer.self_heal("AgentX", IncidentType.UNKNOWN, "Something broke")
        assert result.status == RecoveryStatus.ESCALATED
        assert len(called) == 1
        assert called[0][0] == "AgentX"

    def test_escalation_handler_exception_does_not_crash(self):
        healer = SelfHealer(level=SelfHealLevel.RULE_ONLY)
        healer.load_rules([])
        healer.set_escalation_handler(lambda *a: 1 / 0)
        result = healer.self_heal("A", IncidentType.UNKNOWN, "error")
        assert result.status == RecoveryStatus.ESCALATED


# ── Self Healer: Ledger Learning ───────────────────────────────

class TestSelfHealerLedgerLearning:
    def test_past_success_reused(self):
        db = FakeDB()
        healer = SelfHealer(level=SelfHealLevel.LLM_ASSISTED)
        healer.load_rules([])
        healer.set_database(db)
        # Record a past successful recovery
        past_entry = RecoveryLedgerEntry(
            agent_name="Planner",
            incident_type=IncidentType.EXECUTION_ERROR,
            error_message="RuntimeError in step 3",
            recovery_action=RecoveryActionType.RETRY,
            status=RecoveryStatus.SUCCEEDED,
            confidence=0.85,
            evidence={"strategy": "retry with backoff"},
        )
        healer.ledger.record(past_entry)
        # Now trigger a similar incident
        result = healer.self_heal("Planner", IncidentType.EXECUTION_ERROR,
                                  "RuntimeError in step 5")
        assert result.diagnosed_by == "ledger"
        assert result.action.action_type == RecoveryActionType.RETRY

    def test_ledger_skipped_when_level_too_low(self):
        db = FakeDB()
        healer = SelfHealer(level=SelfHealLevel.RULE_ONLY)
        healer.load_rules([])
        healer.set_database(db)
        past_entry = RecoveryLedgerEntry(
            agent_name="P", incident_type=IncidentType.EXECUTION_ERROR,
            error_message="err", recovery_action=RecoveryActionType.RETRY,
            status=RecoveryStatus.SUCCEEDED, confidence=0.9,
        )
        healer.ledger.record(past_entry)
        result = healer.self_heal("P", IncidentType.EXECUTION_ERROR, "err")
        assert result.diagnosed_by == "system"  # escalated, not ledger


# ── Convenience Functions ──────────────────────────────────────

class TestConvenience:
    def test_get_healer_singleton(self):
        h1 = get_healer()
        h2 = get_healer()
        assert h1 is h2
        assert len(h1.rules) == 10

    def test_self_heal_function(self):
        result = self_heal("Test", "timeout", "Connection timeout")
        assert result.status == RecoveryStatus.ATTEMPTED
        assert result.diagnosed_by == "rule"

    def test_self_heal_invalid_type_falls_to_unknown(self):
        result = self_heal("Test", "nonexistent_type", "some error")
        assert result.incident_type == IncidentType.UNKNOWN

    def test_reset_clears_rules(self):
        healer = SelfHealer()
        healer.load_rules(default_recovery_rules())
        assert len(healer.rules) == 10
        healer.reset()
        assert len(healer.rules) == 0
