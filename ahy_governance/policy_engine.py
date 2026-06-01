"""
Policy Engine — trigger → match → action rule evaluation.

Rules are stored in SQLite and evaluated in-process.
Each rule declares what triggers it, what conditions to match,
and what actions to take.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def _parse_ts(ts: str) -> float:
    try:
        return datetime.fromisoformat(ts).timestamp()
    except (ValueError, TypeError):
        return 0.0

logger = logging.getLogger(__name__)


class TriggerType(Enum):
    COST_SPIKE = "cost_spike"
    BUDGET_WARNING = "budget_warning"
    CONFLICT_DETECTED = "conflict_detected"
    AGENT_OFFLINE = "agent_offline"
    PROMPT_INJECTION = "prompt_injection"
    COMPLIANCE_VIOLATION = "compliance_violation"
    AGENT_ERROR = "agent_error"
    AGENT_LEVEL_EVALUATED = "agent_level_evaluated"
    SELF_HEAL_ESCALATION = "self_heal_escalation"


# ── Agent Level Grading ──────────────────────────────────────────
# Based on agents-best-practices (github.com/DenisSergeevitch/agents-best-practices)
# Maps agent maturity to required governance controls.


class AgentLevel(Enum):
    """Agent maturity levels — from read-only to fully autonomous."""
    LEVEL_0 = 0  # Answer-only, no tools
    LEVEL_1 = 1  # Retrieval (read-only)
    LEVEL_2 = 2  # Drafting (propose, can't commit)
    LEVEL_3 = 3  # Approval-gated actor
    LEVEL_4 = 4  # Policy-bounded autonomous
    LEVEL_5 = 5  # Long-running goal worker


class RiskClass(Enum):
    """Tool risk classification — from agents-best-practices."""
    READ_ONLY = "read_only"
    SEARCH_ONLY = "search_only"
    COMPUTE_ONLY = "compute_only"
    DRAFT_ONLY = "draft_only"
    WRITE_LOCAL = "write_local"
    WRITE_INTERNAL = "write_internal"
    WRITE_EXTERNAL = "write_external"
    FINANCIAL = "financial"
    COMMUNICATION = "communication"
    IDENTITY_ACCESS = "identity_access"
    SECURITY_SENSITIVE = "security_sensitive"
    PROCESS_EXECUTION = "process_execution"
    NETWORK_OPEN_WORLD = "network_open_world"
    DESTRUCTIVE = "destructive"
    PRIVILEGED_ADMIN = "privileged_admin"


@dataclass
class AgentCapabilities:
    """Describes what an agent can do — used to evaluate its level."""
    can_read: bool = False
    can_search: bool = False
    can_draft: bool = False
    can_write_local: bool = False
    can_write_external: bool = False
    can_execute_code: bool = False
    can_use_financial_tools: bool = False
    can_communicate_externally: bool = False
    requires_approval: bool = True  # Does agent need approval for writes?
    has_budget_controls: bool = False
    has_durable_state: bool = False
    has_checkpoint_recovery: bool = False
    max_tool_risk: RiskClass = RiskClass.READ_ONLY

    def to_dict(self) -> dict:
        return {
            "can_read": self.can_read,
            "can_search": self.can_search,
            "can_draft": self.can_draft,
            "can_write_local": self.can_write_local,
            "can_write_external": self.can_write_external,
            "can_execute_code": self.can_execute_code,
            "can_use_financial_tools": self.can_use_financial_tools,
            "can_communicate_externally": self.can_communicate_externally,
            "requires_approval": self.requires_approval,
            "has_budget_controls": self.has_budget_controls,
            "has_durable_state": self.has_durable_state,
            "has_checkpoint_recovery": self.has_checkpoint_recovery,
            "max_tool_risk": self.max_tool_risk.value,
        }

    @classmethod
    def from_dict(cls, d: dict) -> AgentCapabilities:
        risk = d.get("max_tool_risk", "read_only")
        if isinstance(risk, str):
            try:
                risk = RiskClass(risk)
            except ValueError:
                risk = RiskClass.READ_ONLY
        return cls(
            can_read=d.get("can_read", False),
            can_search=d.get("can_search", False),
            can_draft=d.get("can_draft", False),
            can_write_local=d.get("can_write_local", False),
            can_write_external=d.get("can_write_external", False),
            can_execute_code=d.get("can_execute_code", False),
            can_use_financial_tools=d.get("can_use_financial_tools", False),
            can_communicate_externally=d.get("can_communicate_externally", False),
            requires_approval=d.get("requires_approval", True),
            has_budget_controls=d.get("has_budget_controls", False),
            has_durable_state=d.get("has_durable_state", False),
            has_checkpoint_recovery=d.get("has_checkpoint_recovery", False),
            max_tool_risk=risk,
        )


@dataclass
class GovernanceStrategy:
    """Governance controls required for a given agent level."""
    level: AgentLevel
    label: str
    description: str
    required_controls: list[str]
    risk_classes_allowed: list[RiskClass]
    needs_audit: bool = True
    needs_cost_tracking: bool = True
    needs_conflict_detection: bool = False
    needs_anomaly_detection: bool = False
    needs_auto_resolution: bool = False
    needs_prompt_guard: bool = False
    needs_rbac: bool = False
    needs_circuit_breaker: bool = False
    needs_realtime_alerts: bool = False
    needs_human_fallback: bool = False
    needs_self_healing: bool = False
    self_healing_level: str = ""

    def to_dict(self) -> dict:
        return {
            "level": self.level.value,
            "label": self.label,
            "description": self.description,
            "required_controls": self.required_controls,
            "risk_classes_allowed": [r.value for r in self.risk_classes_allowed],
            "needs_audit": self.needs_audit,
            "needs_cost_tracking": self.needs_cost_tracking,
            "needs_conflict_detection": self.needs_conflict_detection,
            "needs_anomaly_detection": self.needs_anomaly_detection,
            "needs_auto_resolution": self.needs_auto_resolution,
            "needs_prompt_guard": self.needs_prompt_guard,
            "needs_rbac": self.needs_rbac,
            "needs_circuit_breaker": self.needs_circuit_breaker,
            "needs_realtime_alerts": self.needs_realtime_alerts,
            "needs_human_fallback": self.needs_human_fallback,
            "needs_self_healing": self.needs_self_healing,
            "self_healing_level": self.self_healing_level,
        }


# ── Level → Strategy mapping ─────────────────────────────────────

AGENT_LEVEL_STRATEGIES: dict[AgentLevel, GovernanceStrategy] = {
    AgentLevel.LEVEL_0: GovernanceStrategy(
        level=AgentLevel.LEVEL_0,
        label="Answer-Only",
        description="No tool execution — pure Q&A, drafting, summarization.",
        required_controls=["audit_log"],
        risk_classes_allowed=[RiskClass.READ_ONLY],
    ),
    AgentLevel.LEVEL_1: GovernanceStrategy(
        level=AgentLevel.LEVEL_1,
        label="Retrieval Agent",
        description="Read-only access to trusted resources, no side effects.",
        required_controls=["audit_log", "cost_tracking", "read_only_permissions"],
        risk_classes_allowed=[RiskClass.READ_ONLY, RiskClass.SEARCH_ONLY],
        needs_cost_tracking=True,
    ),
    AgentLevel.LEVEL_2: GovernanceStrategy(
        level=AgentLevel.LEVEL_2,
        label="Drafting Agent",
        description="Can propose actions and draft outputs, but cannot commit changes.",
        required_controls=["audit_log", "cost_tracking", "draft_gate", "prompt_guard"],
        risk_classes_allowed=[
            RiskClass.READ_ONLY, RiskClass.SEARCH_ONLY,
            RiskClass.COMPUTE_ONLY, RiskClass.DRAFT_ONLY,
        ],
        needs_prompt_guard=True,
    ),
    AgentLevel.LEVEL_3: GovernanceStrategy(
        level=AgentLevel.LEVEL_3,
        label="Approval-Gated Actor",
        description="Can execute actions after explicit approval. Conflict detection active.",
        required_controls=[
            "audit_log", "cost_tracking", "approval_gate",
            "conflict_detection", "prompt_guard", "rbac",
        ],
        risk_classes_allowed=[
            RiskClass.READ_ONLY, RiskClass.SEARCH_ONLY,
            RiskClass.COMPUTE_ONLY, RiskClass.DRAFT_ONLY,
            RiskClass.WRITE_LOCAL, RiskClass.WRITE_INTERNAL,
        ],
        needs_conflict_detection=True,
        needs_prompt_guard=True,
        needs_rbac=True,
        needs_human_fallback=True,
    ),
    AgentLevel.LEVEL_4: GovernanceStrategy(
        level=AgentLevel.LEVEL_4,
        label="Autonomous Actor",
        description="Executes low-risk actions autonomously within strict policy bounds.",
        required_controls=[
            "audit_log", "cost_tracking", "conflict_detection",
            "anomaly_detection", "auto_resolution", "prompt_guard",
            "rbac", "circuit_breaker",
        ],
        risk_classes_allowed=[
            RiskClass.READ_ONLY, RiskClass.SEARCH_ONLY,
            RiskClass.COMPUTE_ONLY, RiskClass.DRAFT_ONLY,
            RiskClass.WRITE_LOCAL, RiskClass.WRITE_INTERNAL,
            RiskClass.WRITE_EXTERNAL,
        ],
        needs_conflict_detection=True,
        needs_anomaly_detection=True,
        needs_auto_resolution=True,
        needs_prompt_guard=True,
        needs_rbac=True,
        needs_circuit_breaker=True,
        needs_human_fallback=True,
        needs_self_healing=True,
        self_healing_level="rule_only",
    ),
    AgentLevel.LEVEL_5: GovernanceStrategy(
        level=AgentLevel.LEVEL_5,
        label="Full Autonomous",
        description="Long-running goal worker with full harness — all controls active.",
        required_controls=[
            "audit_log", "cost_tracking", "conflict_detection",
            "anomaly_detection", "auto_resolution", "prompt_guard",
            "rbac", "circuit_breaker", "realtime_alerts",
            "checkpoint_recovery", "budget_enforcement", "self_healing",
        ],
        risk_classes_allowed=[r for r in RiskClass],  # all risk classes
        needs_conflict_detection=True,
        needs_anomaly_detection=True,
        needs_auto_resolution=True,
        needs_prompt_guard=True,
        needs_rbac=True,
        needs_circuit_breaker=True,
        needs_realtime_alerts=True,
        needs_human_fallback=True,
        needs_self_healing=True,
        self_healing_level="llm_assisted",
    ),
}


def evaluate_agent_level(capabilities: AgentCapabilities) -> AgentLevel:
    """Determine agent level from its capabilities.

    Uses a scoring approach: each capability maps to a minimum level.
    The agent's level is the highest level where it meets ALL requirements.
    """
    # Level 0: default — no capabilities needed
    # Level 1: can_read or can_search
    # Level 2: can_draft + (can_read or can_search)
    # Level 3: can_write_local + requires_approval
    # Level 4: can_write_external + !requires_approval + has_budget_controls
    # Level 5: has_durable_state + has_checkpoint_recovery + can_execute_code

    if (capabilities.has_durable_state
            and capabilities.has_checkpoint_recovery
            and capabilities.can_execute_code
            and not capabilities.requires_approval
            and capabilities.has_budget_controls):
        return AgentLevel.LEVEL_5

    if (capabilities.can_write_external
            and not capabilities.requires_approval
            and capabilities.has_budget_controls):
        return AgentLevel.LEVEL_4

    if (capabilities.can_write_local
            and capabilities.requires_approval):
        return AgentLevel.LEVEL_3

    if capabilities.can_draft and (capabilities.can_read or capabilities.can_search):
        return AgentLevel.LEVEL_2

    if capabilities.can_read or capabilities.can_search:
        return AgentLevel.LEVEL_1

    return AgentLevel.LEVEL_0


def recommend_strategy(level: AgentLevel) -> GovernanceStrategy:
    """Get the recommended governance strategy for an agent level."""
    return AGENT_LEVEL_STRATEGIES[level]


def level_policy_rules() -> list[PolicyRule]:
    """Generate default policy rules based on agent levels."""
    return [
        PolicyRule(
            id="level-3-plus-conflict-detection",
            name="Level 3+ Conflict Detection",
            description="Agents at Level 3+ must have conflict detection enabled",
            trigger=TriggerType.AGENT_LEVEL_EVALUATED,
            match_conditions=[
                MatchCondition(field="agent_level", operator="gte", value=3),
                MatchCondition(field="has_conflict_detection", operator="eq", value=False),
            ],
            actions=[ActionType.ALERT, ActionType.LOG],
        ),
        PolicyRule(
            id="level-4-plus-anomaly-detection",
            name="Level 4+ Anomaly Detection",
            description="Agents at Level 4+ must have anomaly detection enabled",
            trigger=TriggerType.AGENT_LEVEL_EVALUATED,
            match_conditions=[
                MatchCondition(field="agent_level", operator="gte", value=4),
                MatchCondition(field="has_anomaly_detection", operator="eq", value=False),
            ],
            actions=[ActionType.ALERT, ActionType.LOG],
        ),
        PolicyRule(
            id="level-5-circuit-breaker",
            name="Level 5 Circuit Breaker Required",
            description="Level 5 agents must have circuit breaker enabled",
            trigger=TriggerType.AGENT_LEVEL_EVALUATED,
            match_conditions=[
                MatchCondition(field="agent_level", operator="eq", value=5),
                MatchCondition(field="has_circuit_breaker", operator="eq", value=False),
            ],
            actions=[ActionType.BLOCK, ActionType.ALERT],
        ),
        PolicyRule(
            id="unapproved-external-write",
            name="Unapproved External Write Block",
            description="Agents without approval gate cannot perform external writes",
            trigger=TriggerType.AGENT_LEVEL_EVALUATED,
            match_conditions=[
                MatchCondition(field="can_write_external", operator="eq", value=True),
                MatchCondition(field="requires_approval", operator="eq", value=False),
                MatchCondition(field="agent_level", operator="lt", value=4),
            ],
            actions=[ActionType.BLOCK, ActionType.ALERT],
        ),
        PolicyRule(
            id="no-budget-autonomous-block",
            name="No Budget Autonomous Block",
            description="Autonomous agents (Level 4+) without budget controls are blocked",
            trigger=TriggerType.AGENT_LEVEL_EVALUATED,
            match_conditions=[
                MatchCondition(field="agent_level", operator="gte", value=4),
                MatchCondition(field="has_budget_controls", operator="eq", value=False),
            ],
            actions=[ActionType.BLOCK, ActionType.ALERT],
        ),
    ]


class ActionType(Enum):
    ALERT = "alert"
    BLOCK = "block"
    LOG = "log"
    THROTTLE = "throttle"


class RuleStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    TRIGGERED = "triggered"


@dataclass
class MatchCondition:
    field: str
    operator: str  # gt, lt, eq, gte, lte, contains, regex
    value: Any

    def evaluate(self, context: dict) -> bool:
        actual = context.get(self.field)
        if actual is None:
            return False
        try:
            if self.operator == "gt":
                return float(actual) > float(self.value)
            elif self.operator == "lt":
                return float(actual) < float(self.value)
            elif self.operator == "eq":
                return str(actual).lower() == str(self.value).lower()
            elif self.operator == "gte":
                return float(actual) >= float(self.value)
            elif self.operator == "lte":
                return float(actual) <= float(self.value)
            elif self.operator == "contains":
                return str(self.value).lower() in str(actual).lower()
        except (ValueError, TypeError):
            return False
        return False


@dataclass
class PolicyRule:
    id: str
    name: str
    description: str
    trigger: TriggerType
    match_conditions: list[MatchCondition] = field(default_factory=list)
    actions: list[ActionType] = field(default_factory=list)
    enabled: bool = True
    cooldown_seconds: int = 300
    _last_triggered: str = ""

    def evaluate(self, trigger: TriggerType, context: dict) -> list[ActionType]:
        if not self.enabled:
            return []
        if self.trigger != trigger:
            return []
        if not all(c.evaluate(context) for c in self.match_conditions):
            return []
        # Cooldown check
        if self.cooldown_seconds > 0 and self._last_triggered:
            elapsed = _utc_ts() - _parse_ts(self._last_triggered)
            if elapsed < self.cooldown_seconds:
                return []
        self._last_triggered = _utc_now()
        return list(dict.fromkeys(self.actions))  # deduplicate

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "trigger": self.trigger.value,
            "match": [{"field": c.field, "operator": c.operator, "value": c.value}
                      for c in self.match_conditions],
            "actions": [a.value for a in self.actions],
            "enabled": self.enabled,
            "cooldown_seconds": self.cooldown_seconds,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PolicyRule:
        try:
            return cls(
                id=d.get("id", ""),
                name=d.get("name", "unnamed"),
                description=d.get("description", ""),
                trigger=TriggerType(d.get("trigger", "cost_spike")),
                match_conditions=[MatchCondition(**m) for m in d.get("match", [])],
                actions=[ActionType(a) for a in d.get("actions", [])],
                enabled=d.get("enabled", True),
                cooldown_seconds=d.get("cooldown_seconds", 300),
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.warning("Invalid policy rule dict: %s — %s", d.get("id", "?"), e)
            return cls(id="invalid", name="Invalid Rule", trigger=TriggerType.COST_SPIKE,
                       enabled=False, description=f"Failed to load: {e}")


class PolicyEngine:
    """Central policy evaluation engine.

    Usage:
        engine = PolicyEngine()
        engine.load_rules(db)  # Load from SQLite

        # When something happens:
        actions = engine.evaluate(
            trigger=TriggerType.COST_SPIKE,
            context={"agent_name": "Planner", "cost_usd": 5.2, "threshold_usd": 2.0},
        )
        for action in actions:
            if action == ActionType.BLOCK:
                ...
    """

    def __init__(self):
        self._rules: list[PolicyRule] = []
        self._action_handlers: dict[ActionType, list[Callable]] = {}

    def load_rules(self, rules: list[PolicyRule]):
        self._rules = rules

    def register_handler(self, action: ActionType, handler: Callable):
        """Register a callback for when an action is triggered."""
        self._action_handlers.setdefault(action, []).append(handler)

    def evaluate(self, trigger: TriggerType, context: dict) -> list[ActionType]:
        actions: list[ActionType] = []
        for rule in self._rules:
            matched = rule.evaluate(trigger, context)
            for action in matched:
                actions.append(action)
                for handler in self._action_handlers.get(action, []):
                    try:
                        handler(rule, context)
                    except Exception:
                        logger.exception("Policy action handler failed")
        return actions

    @property
    def rules(self) -> list[PolicyRule]:
        return self._rules

    def rule_by_id(self, rule_id: str) -> PolicyRule | None:
        for r in self._rules:
            if r.id == rule_id:
                return r
        return None


# ── Built-in default rules ──────────────────────────────────────

def default_rules() -> list[PolicyRule]:
    return [
        PolicyRule(
            id="cost-spike-block",
            name="成本异常自动阻断",
            description="单次调用成本超过阈值时自动拦截",
            trigger=TriggerType.COST_SPIKE,
            match_conditions=[
                MatchCondition(field="cost_usd", operator="gte", value=2.0),
            ],
            actions=[ActionType.BLOCK, ActionType.ALERT],
        ),
        PolicyRule(
            id="budget-warning-alert",
            name="预算告警通知",
            description="预算使用超过告警阈值时发送通知",
            trigger=TriggerType.BUDGET_WARNING,
            match_conditions=[
                MatchCondition(field="usage_pct", operator="gte", value=80),
            ],
            actions=[ActionType.ALERT],
        ),
        PolicyRule(
            id="conflict-critical-block",
            name="严重冲突阻断",
            description="检测到 CRITICAL 级别冲突时阻断下游执行",
            trigger=TriggerType.CONFLICT_DETECTED,
            match_conditions=[
                MatchCondition(field="severity", operator="eq", value="CRITICAL"),
            ],
            actions=[ActionType.BLOCK, ActionType.ALERT],
        ),
        PolicyRule(
            id="agent-offline-alert",
            name="Agent 离线告警",
            description="Agent 超过 5 分钟无心跳时发送通知",
            trigger=TriggerType.AGENT_OFFLINE,
            match_conditions=[],
            actions=[ActionType.ALERT],
        ),
        PolicyRule(
            id="injection-block",
            name="注入攻击拦截",
            description="检测到 Prompt 注入攻击时自动阻断",
            trigger=TriggerType.PROMPT_INJECTION,
            match_conditions=[
                MatchCondition(field="confidence", operator="gte", value=0.7),
            ],
            actions=[ActionType.BLOCK, ActionType.ALERT, ActionType.LOG],
        ),
        *level_policy_rules(),
    ]


# ── Singleton ───────────────────────────────────────────────────

_engine: PolicyEngine | None = None


def get_policy_engine() -> PolicyEngine:
    global _engine
    if _engine is None:
        _engine = PolicyEngine()
        _engine.load_rules(default_rules())
    return _engine
