"""
Self Healer — Agent 自愈引擎

特性:
  3 级自愈策略: rule_only / llm_assisted / full_auto
  分层升级: Watchdog → Rules → Recovery Ledger → LLM Doctor → 人工
  Recovery Ledger: 从每次事件中学习，复用历史成功策略

设计:
  - RuleEngine 纯正则匹配，零外部依赖
  - LLMDoctor 为抽象接口，通过 set_diagnose_fn() 插拔
  - RecoveryLedger 持久化到 SQLite，支持相似事件检索
  - 所有恢复操作通过 AuditReporter 记录审计
  - 冷却期防止恢复循环（thundering herd）

用法:
  healer = get_healer()
  healer.configure(level=SelfHealLevel.LLM_ASSISTED)
  result = healer.self_heal(
      agent_name="Planner",
      incident_type=IncidentType.TIMEOUT,
      error_message="Request timed out after 30s",
  )
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from .conflict_detector import Severity


# ── Enums ───────────────────────────────────────────────────────

class SelfHealLevel(Enum):
    RULE_ONLY = "rule_only"
    LLM_ASSISTED = "llm_assisted"
    FULL_AUTO = "full_auto"


class RecoveryActionType(Enum):
    RETRY = "retry"
    CIRCUIT_BREAK = "circuit_break"
    ROLLBACK = "rollback"
    MODEL_FALLBACK = "model_fallback"
    CONTEXT_TRUNCATE = "context_truncate"
    OUTPUT_VALIDATE = "output_validate"
    RESTART_AGENT = "restart_agent"
    ALERT_HUMAN = "alert_human"


class IncidentType(Enum):
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    AUTH_ERROR = "auth_error"
    TOKEN_SPIKE = "token_spike"
    MEMORY_EXHAUSTED = "memory_exhausted"
    DEPENDENCY_FAILURE = "dependency_failure"
    OUTPUT_INVALID = "output_invalid"
    HALLUCINATION = "hallucination"
    EXECUTION_ERROR = "execution_error"
    UNKNOWN = "unknown"


class RecoveryStatus(Enum):
    ATTEMPTED = "attempted"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ESCALATED = "escalated"
    SKIPPED = "skipped"


# ── Data Classes ────────────────────────────────────────────────

@dataclass
class RecoveryAction:
    action_type: RecoveryActionType
    description: str
    params: dict = field(default_factory=dict)
    confidence: float = 0.0
    source: str = "rule"

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type.value,
            "description": self.description,
            "params": self.params,
            "confidence": self.confidence,
            "source": self.source,
        }


@dataclass
class RecoveryRule:
    id: str
    name: str
    incident_type: IncidentType
    pattern: str
    recovery_action_type: RecoveryActionType
    priority: int = 50
    cooldown_seconds: int = 300
    enabled: bool = True
    conditions: dict = field(default_factory=dict)
    _last_triggered: float = 0.0

    def match(self, incident_type: IncidentType, error_message: str) -> bool:
        if not self.enabled:
            return False
        if self.incident_type != incident_type and self.incident_type != IncidentType.UNKNOWN:
            return False
        if not re.search(self.pattern, error_message):
            return False
        if self.cooldown_seconds > 0:
            elapsed = time.time() - self._last_triggered
            if elapsed < self.cooldown_seconds:
                return False
        return True

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name,
            "incident_type": self.incident_type.value,
            "pattern": self.pattern,
            "action": self.recovery_action_type.value,
            "priority": self.priority,
            "cooldown_seconds": self.cooldown_seconds,
            "enabled": self.enabled,
        }


@dataclass
class RecoveryLedgerEntry:
    incident_id: int = 0
    agent_name: str = ""
    incident_type: IncidentType = IncidentType.UNKNOWN
    error_message: str = ""
    recovery_action: RecoveryActionType = RecoveryActionType.ALERT_HUMAN
    status: RecoveryStatus = RecoveryStatus.ATTEMPTED
    diagnosed_by: str = "rule"
    confidence: float = 0.0
    evidence: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "agent_name": self.agent_name,
            "incident_type": self.incident_type.value,
            "error_message": self.error_message,
            "recovery_action": self.recovery_action.value,
            "status": self.status.value,
            "diagnosed_by": self.diagnosed_by,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
        }


@dataclass
class HealResult:
    agent_name: str
    incident_type: IncidentType
    action: RecoveryAction | None = None
    status: RecoveryStatus = RecoveryStatus.SKIPPED
    diagnosed_by: str = ""
    ledger_entry: RecoveryLedgerEntry | None = None
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "incident_type": self.incident_type.value,
            "action": self.action.to_dict() if self.action else None,
            "status": self.status.value,
            "diagnosed_by": self.diagnosed_by,
            "detail": self.detail,
        }


# ── Rule Engine ────────────────────────────────────────────────

class RuleEngine:
    """Pure pattern-matching engine for known failure types."""

    def __init__(self):
        self._rules: list[RecoveryRule] = []

    def load_rules(self, rules: list[RecoveryRule]):
        self._rules = sorted(rules, key=lambda r: r.priority)

    def match(self, incident_type: IncidentType, error_message: str) -> RecoveryRule | None:
        for rule in self._rules:
            if rule.match(incident_type, error_message):
                rule._last_triggered = time.time()
                return rule
        return None

    @property
    def rules(self) -> list[RecoveryRule]:
        return list(self._rules)


# ── LLM Doctor ─────────────────────────────────────────────────

class LLMDoctor:
    """Abstract LLM-assisted diagnosis interface.

    The actual LLM call is pluggable via the ``diagnose_fn`` callback.
    Clients wire in their own LLM (Claude API, GPT-4, etc.).

    Signature: (error_message: str, context: dict) -> RecoveryAction | None
    """

    def __init__(self):
        self._diagnose_fn: Callable | None = None

    def set_diagnose_fn(self, fn: Callable[[str, dict], RecoveryAction | None]):
        self._diagnose_fn = fn

    def diagnose(
        self, agent_name: str, incident_type: IncidentType,
        error_message: str, context: dict,
    ) -> RecoveryAction | None:
        if self._diagnose_fn is None:
            return None
        try:
            return self._diagnose_fn(error_message, {
                "agent_name": agent_name,
                "incident_type": incident_type.value,
                **context,
            })
        except Exception:
            return None


# ── Recovery Ledger ────────────────────────────────────────────

class RecoveryLedger:
    """Persistent recovery event store. Learns from every incident."""

    def __init__(self):
        self._db = None

    def set_database(self, db):
        self._db = db

    def record(self, entry: RecoveryLedgerEntry, workspace_id: str = "") -> int:
        if self._db and self._db.enabled:
            return self._db.recovery_ledger_insert(
                agent_name=entry.agent_name,
                incident_type=entry.incident_type.value,
                error_message=entry.error_message,
                recovery_action=entry.recovery_action.value,
                diagnosed_by=entry.diagnosed_by,
                success=entry.status == RecoveryStatus.SUCCEEDED,
                confidence=entry.confidence,
                evidence=json.dumps(entry.evidence, ensure_ascii=False),
                timestamp=entry.timestamp,
                workspace_id=workspace_id,
            )
        return 0

    def find_similar(
        self, incident_type: IncidentType, error_message: str,
        workspace_id: str = "", limit: int = 5,
    ) -> list[dict]:
        if self._db and self._db.enabled:
            return self._db.recovery_ledger_similar(
                incident_type.value, error_message, workspace_id, limit,
            )
        return []

    def query(
        self, agent_name: str = "", incident_type: str = "",
        workspace_id: str = "", limit: int = 100,
    ) -> list[dict]:
        if self._db and self._db.enabled:
            return self._db.recovery_ledger_list(
                agent_name, incident_type, workspace_id, limit,
            )
        return []


# ── Self Healer ────────────────────────────────────────────────

class SelfHealer:
    """Self-healing orchestrator with layered escalation."""

    def __init__(self, level: SelfHealLevel = SelfHealLevel.RULE_ONLY):
        self.level = level
        self._rule_engine = RuleEngine()
        self._llm_doctor = LLMDoctor()
        self._ledger = RecoveryLedger()
        self._on_escalate: Callable | None = None

    # ── Configuration ──────────────────────────────────────────

    def set_database(self, db):
        self._ledger.set_database(db)

    def set_llm_doctor(self, doctor: LLMDoctor):
        self._llm_doctor = doctor

    def set_escalation_handler(self, handler: Callable):
        self._on_escalate = handler

    def load_rules(self, rules: list[RecoveryRule]):
        self._rule_engine.load_rules(rules)

    @property
    def ledger(self) -> RecoveryLedger:
        return self._ledger

    @property
    def rules(self) -> list[RecoveryRule]:
        return self._rule_engine.rules

    # ── Core ───────────────────────────────────────────────────

    def self_heal(
        self, agent_name: str, incident_type: IncidentType,
        error_message: str, context: dict | None = None,
        workspace_id: str = "",
    ) -> HealResult:
        """Attempt self-healing with progressive escalation."""
        context = context or {}

        # Step 1: Rule Engine
        rule = self._rule_engine.match(incident_type, error_message)
        if rule is not None:
            action = RecoveryAction(
                action_type=rule.recovery_action_type,
                description=rule.name,
                params=rule.conditions,
                confidence=0.85,
                source="rule",
            )
            return self._finalize(
                agent_name, incident_type, error_message, action,
                RecoveryStatus.ATTEMPTED, "rule", workspace_id, context,
            )

        # Step 2: Recovery Ledger lookup
        if self.level in (SelfHealLevel.LLM_ASSISTED, SelfHealLevel.FULL_AUTO):
            similar = self._ledger.find_similar(incident_type, error_message, workspace_id)
            if similar:
                best = similar[0]
                if best.get("success"):
                    action = RecoveryAction(
                        action_type=RecoveryActionType(best["recovery_action"]),
                        description=f"从历史记录学习: {best['recovery_action']}",
                        params=json.loads(best.get("evidence", "{}")),
                        confidence=min(best.get("confidence", 0.5) + 0.1, 0.9),
                        source="ledger",
                    )
                    return self._finalize(
                        agent_name, incident_type, error_message, action,
                        RecoveryStatus.ATTEMPTED, "ledger", workspace_id, context,
                    )

        # Step 3: LLM Doctor
        if self.level in (SelfHealLevel.LLM_ASSISTED, SelfHealLevel.FULL_AUTO):
            llm_action = self._llm_doctor.diagnose(
                agent_name, incident_type, error_message, context,
            )
            if llm_action is not None:
                llm_action.source = "llm"
                status = (RecoveryStatus.ATTEMPTED if self.level == SelfHealLevel.FULL_AUTO
                          else RecoveryStatus.ESCALATED)
                return self._finalize(
                    agent_name, incident_type, error_message, llm_action,
                    status, "llm", workspace_id, context,
                )

        # Step 4: Escalate to human
        return self._escalate(
            agent_name, incident_type, error_message, workspace_id, context,
        )

    # ── Internal ───────────────────────────────────────────────

    def _finalize(
        self, agent_name: str, incident_type: IncidentType,
        error_message: str, action: RecoveryAction, status: RecoveryStatus,
        diagnosed_by: str, workspace_id: str, context: dict,
    ) -> HealResult:
        entry = RecoveryLedgerEntry(
            agent_name=agent_name,
            incident_type=incident_type,
            error_message=error_message,
            recovery_action=action.action_type,
            status=status,
            diagnosed_by=diagnosed_by,
            confidence=action.confidence,
            evidence=context,
        )
        entry.incident_id = self._ledger.record(entry, workspace_id)
        self._audit(agent_name, incident_type, action, status, workspace_id)
        return HealResult(
            agent_name=agent_name, incident_type=incident_type,
            action=action, status=status, diagnosed_by=diagnosed_by,
            ledger_entry=entry,
            detail=f"{diagnosed_by} → {action.action_type.value}: {action.description}",
        )

    def _escalate(
        self, agent_name: str, incident_type: IncidentType,
        error_message: str, workspace_id: str, context: dict,
    ) -> HealResult:
        action = RecoveryAction(
            action_type=RecoveryActionType.ALERT_HUMAN,
            description="自动恢复失败，升级到人工处理",
            source="system",
        )
        entry = RecoveryLedgerEntry(
            agent_name=agent_name,
            incident_type=incident_type,
            error_message=error_message,
            recovery_action=RecoveryActionType.ALERT_HUMAN,
            status=RecoveryStatus.ESCALATED,
            diagnosed_by="system",
            confidence=1.0,
            evidence=context,
        )
        entry.incident_id = self._ledger.record(entry, workspace_id)
        if self._on_escalate:
            try:
                self._on_escalate(agent_name, incident_type, error_message, context)
            except Exception:
                pass
        self._audit(agent_name, incident_type, action, RecoveryStatus.ESCALATED, workspace_id)
        return HealResult(
            agent_name=agent_name, incident_type=incident_type,
            action=action, status=RecoveryStatus.ESCALATED, diagnosed_by="system",
            ledger_entry=entry,
            detail=f"已升级到人工: {error_message[:100]}",
        )

    def _audit(self, agent_name: str, incident_type: IncidentType,
               action: RecoveryAction, status: RecoveryStatus, workspace_id: str):
        from .audit_logger import AuditEventType, get_auditor
        auditor = get_auditor()
        event_map = {
            RecoveryStatus.SUCCEEDED: AuditEventType.SELF_HEAL_SUCCEEDED,
            RecoveryStatus.ESCALATED: AuditEventType.SELF_HEAL_ESCALATED,
            RecoveryStatus.FAILED: AuditEventType.SELF_HEAL_FAILED,
        }
        event_type = event_map.get(status, AuditEventType.SELF_HEAL_ATTEMPTED)
        auditor.log(
            event_type, agent_name,
            details={
                "incident_type": incident_type.value,
                "action": action.action_type.value,
                "source": action.source,
                "confidence": action.confidence,
                "workspace_id": workspace_id,
            },
        )

    def reset(self):
        self._rule_engine = RuleEngine()


# ── Module-level convenience ────────────────────────────────────

_healer: SelfHealer | None = None


def get_healer() -> SelfHealer:
    """Return the module-level SelfHealer singleton, pre-loaded with default rules."""
    global _healer
    if _healer is None:
        _healer = SelfHealer()
        from .recovery_rules import default_recovery_rules
        _healer.load_rules(default_recovery_rules())
    return _healer


def self_heal(
    agent_name: str, incident_type: str, error_message: str,
    context: dict | None = None, workspace_id: str = "",
) -> HealResult:
    """Convenience: trigger self-healing for an agent."""
    try:
        it = IncidentType(incident_type)
    except ValueError:
        it = IncidentType.UNKNOWN
    return get_healer().self_heal(agent_name, it, error_message, context, workspace_id)
