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
    ]


# ── Singleton ───────────────────────────────────────────────────

_engine: PolicyEngine | None = None


def get_policy_engine() -> PolicyEngine:
    global _engine
    if _engine is None:
        _engine = PolicyEngine()
        _engine.load_rules(default_rules())
    return _engine
