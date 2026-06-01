"""
Recovery Rules — 自愈规则库

内置常见故障模式与恢复策略，RuleEngine 按优先级匹配执行。

用法:
  rules = default_recovery_rules()
  engine = RuleEngine()
  engine.load_rules(rules)
  action = engine.match(IncidentType.TIMEOUT, "Request timed out after 30s")
"""

from __future__ import annotations

from .self_healer import RecoveryRule, RecoveryActionType, IncidentType


def default_recovery_rules() -> list[RecoveryRule]:
    """Return the 10 built-in recovery rules, sorted by priority (lowest = first)."""
    return [
        RecoveryRule(
            id="auth-escalate-human",
            name="认证失败人工介入",
            incident_type=IncidentType.AUTH_ERROR,
            pattern=r"(?i)(401|403|unauthorized|forbidden|auth.*fail|invalid.*key)",
            recovery_action_type=RecoveryActionType.ALERT_HUMAN,
            priority=5,
            cooldown_seconds=600,
        ),
        RecoveryRule(
            id="timeout-retry",
            name="超时重试",
            incident_type=IncidentType.TIMEOUT,
            pattern=r"(?i)(timeout|timed?\s*out|deadline exceeded)",
            recovery_action_type=RecoveryActionType.RETRY,
            priority=10,
            cooldown_seconds=60,
            conditions={"max_retries": 3, "backoff_seconds": 2},
        ),
        RecoveryRule(
            id="rate-limit-backoff",
            name="限流退避",
            incident_type=IncidentType.RATE_LIMIT,
            pattern=r"(?i)(rate.?limit|too many requests|429|quota exceeded)",
            recovery_action_type=RecoveryActionType.CIRCUIT_BREAK,
            priority=10,
            cooldown_seconds=300,
            conditions={"backoff_seconds": 30, "half_open_after": 120},
        ),
        RecoveryRule(
            id="dependency-rollback-retry",
            name="依赖失败回滚重试",
            incident_type=IncidentType.DEPENDENCY_FAILURE,
            pattern=r"(?i)(dependency.*fail|upstream.*error|service unavailable|503)",
            recovery_action_type=RecoveryActionType.ROLLBACK,
            priority=15,
            cooldown_seconds=120,
        ),
        RecoveryRule(
            id="memory-restart",
            name="内存耗尽重启",
            incident_type=IncidentType.MEMORY_EXHAUSTED,
            pattern=r"(?i)(out of memory|OOM|memory.*error|allocation failed)",
            recovery_action_type=RecoveryActionType.RESTART_AGENT,
            priority=20,
            cooldown_seconds=600,
        ),
        RecoveryRule(
            id="hallucination-fallback",
            name="幻觉检测模型降级",
            incident_type=IncidentType.HALLUCINATION,
            pattern=r"(?i)(hallucinat|factual.*error|contradict|made.?up)",
            recovery_action_type=RecoveryActionType.MODEL_FALLBACK,
            priority=25,
            cooldown_seconds=300,
        ),
        RecoveryRule(
            id="token-spike-truncate",
            name="Token暴涨上下文裁剪",
            incident_type=IncidentType.TOKEN_SPIKE,
            pattern=r"(?i)(token.*limit|context.*length|max.*tokens|context.*overflow)",
            recovery_action_type=RecoveryActionType.CONTEXT_TRUNCATE,
            priority=30,
            cooldown_seconds=120,
        ),
        RecoveryRule(
            id="output-validate",
            name="输出校验失败回退",
            incident_type=IncidentType.OUTPUT_INVALID,
            pattern=r"(?i)(invalid.*output|schema.*mismatch|validation.*(error|fail))",
            recovery_action_type=RecoveryActionType.OUTPUT_VALIDATE,
            priority=40,
            cooldown_seconds=60,
        ),
        RecoveryRule(
            id="execution-retry",
            name="执行错误重试",
            incident_type=IncidentType.EXECUTION_ERROR,
            pattern=r"(?i)(execution.*fail|runtime.*error|exception|traceback)",
            recovery_action_type=RecoveryActionType.RETRY,
            priority=50,
            cooldown_seconds=30,
            conditions={"max_retries": 2},
        ),
        RecoveryRule(
            id="unknown-escalate",
            name="未知故障人工升级",
            incident_type=IncidentType.UNKNOWN,
            pattern=r".*",
            recovery_action_type=RecoveryActionType.ALERT_HUMAN,
            priority=100,
            cooldown_seconds=600,
        ),
    ]
