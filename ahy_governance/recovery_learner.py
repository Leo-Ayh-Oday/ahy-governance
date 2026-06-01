"""
Recovery Learner — 自愈规则学习 Agent

独立 Agent，定期扫描 Recovery Ledger 中的成功修复记录，
从 LLM 诊断经验中提炼新规则，自动扩充规则库。

核心能力:
  - 按 (incident_type, recovery_action) 聚类成功案例
  - 从错误消息中提取公共正则模式
  - 达标后生成新 RecoveryRule 加入规则引擎
  - 持久化到 recovery_rules 表，跨会话复用

用法:
  learner = get_learner()
  learner.configure(min_occurrences=3, min_confidence=0.7)
  new_rules = learner.scan_and_learn()
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .self_healer import (
    RecoveryRule, RecoveryActionType, IncidentType, RuleEngine,
)
from .conflict_detector import Severity


# ── Data Classes ────────────────────────────────────────────────

@dataclass
class LearnResult:
    """一次 scan_and_learn() 的产出."""
    new_rules: list[RecoveryRule] = field(default_factory=list)
    updated_rules: list[RecoveryRule] = field(default_factory=list)
    scanned_entries: int = 0
    clusters_found: int = 0
    skipped: int = 0
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "new_rules": [r.to_dict() for r in self.new_rules],
            "updated_rules": [r.to_dict() for r in self.updated_rules],
            "scanned_entries": self.scanned_entries,
            "clusters_found": self.clusters_found,
            "skipped": self.skipped,
            "detail": self.detail,
        }


# ── Pattern Extraction ──────────────────────────────────────────

def _extract_pattern(error_messages: list[str]) -> str:
    """从一组错误消息中提取公共正则模式.

    策略: 找出现最多的关键词（至少2个），构建 OR 模式。
    如果消息太少或差异太大，返回通用模式。
    """
    if not error_messages:
        return r".*"
    if len(error_messages) == 1:
        words = re.findall(r'[a-zA-Z_]\w+', error_messages[0])
        if words:
            return r"(?i)(" + "|".join(re.escape(w) for w in words[:5]) + ")"
        return r".*"

    # 多消息: 找公共词
    word_sets = []
    for msg in error_messages:
        words = set(
            w.lower() for w in re.findall(r'[a-zA-Z_]\w{3,}', msg)
            if w.lower() not in _STOP_WORDS
        )
        word_sets.append(words)

    if not word_sets:
        return r".*"

    # 至少在 60% 的消息里出现的单词
    threshold = max(2, int(len(error_messages) * 0.6))
    common: dict[str, int] = {}
    for ws in word_sets:
        for w in ws:
            common[w] = common.get(w, 0) + 1

    top_words = sorted(
        [w for w, c in common.items() if c >= threshold],
        key=lambda w: common[w], reverse=True,
    )[:8]

    if not top_words:
        return r".*"

    return r"(?i)(" + "|".join(re.escape(w) for w in top_words) + ")"


_STOP_WORDS = {
    "the", "and", "for", "was", "with", "this", "that", "from",
    "has", "have", "been", "error", "failed", "failure", "occurred",
}


# ── Recovery Learner ────────────────────────────────────────────

class RecoveryLearner:
    """独立学习 Agent — 从 Recovery Ledger 提炼规则.

    用法:
        learner = RecoveryLearner()
        learner.set_database(db)
        learner.set_rule_engine(engine)
        result = learner.scan_and_learn()
    """

    def __init__(
        self,
        min_occurrences: int = 3,
        min_confidence: float = 0.7,
        min_success_rate: float = 0.6,
    ):
        self.min_occurrences = min_occurrences
        self.min_confidence = min_confidence
        self.min_success_rate = min_success_rate
        self._db = None
        self._rule_engine: RuleEngine | None = None

    def set_database(self, db):
        self._db = db

    def set_rule_engine(self, engine: RuleEngine):
        self._rule_engine = engine

    # ── Core ───────────────────────────────────────────────────

    def scan_and_learn(self, workspace_id: str = "") -> LearnResult:
        """扫描 Recovery Ledger，提炼新规则.

        流程:
        1. 查询 ledger 中 diagnosed_by=llm 的成功记录
        2. 按 (incident_type, recovery_action) 聚类
        3. 对达标聚类 → 提取模式 → 生成规则
        4. Upsert 到 DB + 加载到 RuleEngine
        """
        entries = self._fetch_ledger_entries(workspace_id)
        if not entries:
            return LearnResult(
                scanned_entries=0,
                detail="No ledger entries found — nothing to learn from",
            )

        # Group by (incident_type, recovery_action)
        clusters: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for e in entries:
            key = (e.get("incident_type", "unknown"), e.get("recovery_action", ""))
            clusters[key].append(e)

        result = LearnResult(
            scanned_entries=len(entries),
            clusters_found=len(clusters),
        )

        new_rules = []
        for (inc_type, rec_action), group in clusters.items():
            # Filter: non-rule diagnoses with high confidence
            # (llm=LLM diagnosed, ledger=learned from history)
            non_rule_entries = [
                e for e in group
                if e.get("diagnosed_by") in ("llm", "ledger")
                and e.get("success") == 1
                and e.get("confidence", 0) >= self.min_confidence
            ]
            if len(non_rule_entries) < self.min_occurrences:
                result.skipped += 1
                continue

            # Check if a rule already exists for this
            if self._rule_engine:
                existing = self._rule_engine.match(
                    IncidentType(inc_type) if inc_type != "unknown"
                    else IncidentType.UNKNOWN,
                    non_rule_entries[0].get("error_message", ""),
                )
                if existing and existing.id != "unknown-escalate":
                    result.skipped += 1
                    continue

            # Extract pattern from error messages
            error_msgs = [e.get("error_message", "") for e in non_rule_entries]
            pattern = _extract_pattern(error_msgs)
            rule_name = self._generate_rule_name(inc_type, rec_action, non_rule_entries)

            avg_confidence = sum(e.get("confidence", 0) for e in non_rule_entries) / len(non_rule_entries)
            priority = self._compute_priority(inc_type, len(non_rule_entries), avg_confidence)

            rule = RecoveryRule(
                id=f"learned-{inc_type}-{rec_action}",
                name=rule_name,
                incident_type=IncidentType(inc_type) if inc_type != "unknown"
                else IncidentType.UNKNOWN,
                pattern=pattern,
                recovery_action_type=RecoveryActionType(rec_action),
                priority=priority,
                cooldown_seconds=120,
            )
            new_rules.append(rule)

            # Persist to DB
            self._persist_rule(rule, workspace_id)

            # Load into engine
            if self._rule_engine:
                self._rule_engine.load_rules([rule])

        result.new_rules = new_rules
        result.detail = (
            f"扫描 {len(entries)} 条记录, 发现 {len(clusters)} 个聚类, "
            f"生成 {len(new_rules)} 条新规则, 跳过 {result.skipped} 个"
        )
        return result

    # ── Internal ───────────────────────────────────────────────

    def _fetch_ledger_entries(self, workspace_id: str) -> list[dict]:
        if self._db and self._db.enabled:
            return self._db.recovery_ledger_list(
                workspace_id=workspace_id, limit=500,
            )
        return []

    def _persist_rule(self, rule: RecoveryRule, workspace_id: str):
        if self._db and self._db.enabled:
            try:
                self._db.recovery_rules_upsert(
                    rule_id=rule.id,
                    name=rule.name,
                    incident_type=rule.incident_type.value,
                    pattern=rule.pattern,
                    recovery_action=rule.recovery_action_type.value,
                    priority=rule.priority,
                    cooldown_seconds=rule.cooldown_seconds,
                    enabled=True,
                    workspace_id=workspace_id,
                )
            except Exception:
                pass

    @staticmethod
    def _generate_rule_name(
        inc_type: str, rec_action: str, entries: list[dict],
    ) -> str:
        action_cn = {
            "retry": "重试", "circuit_break": "熔断",
            "rollback": "回滚", "model_fallback": "模型降级",
            "context_truncate": "裁剪上下文", "output_validate": "输出校验",
            "restart_agent": "重启Agent", "alert_human": "人工介入",
        }
        inc_cn = {
            "timeout": "超时", "rate_limit": "限流",
            "auth_error": "认证失败", "token_spike": "Token溢出",
            "memory_exhausted": "内存耗尽",
            "dependency_failure": "依赖失败",
            "output_invalid": "输出无效", "hallucination": "幻觉",
            "execution_error": "执行错误", "unknown": "未知故障",
        }
        action_label = action_cn.get(rec_action, rec_action)
        inc_label = inc_cn.get(inc_type, inc_type)
        return f"[学习] {inc_label} → {action_label} (×{len(entries)})"

    @staticmethod
    def _compute_priority(
        inc_type: str, occurrences: int, avg_confidence: float,
    ) -> int:
        # Base priority by incident severity
        base = {
            "auth_error": 5, "memory_exhausted": 15, "rate_limit": 10,
            "timeout": 10, "dependency_failure": 15, "hallucination": 25,
            "token_spike": 30, "output_invalid": 40, "execution_error": 45,
            "unknown": 90,
        }.get(inc_type, 60)

        # Bonus: more occurrences + higher confidence → higher priority (lower number)
        bonus = max(0, min(20, int(occurrences * 2) + int(avg_confidence * 10)))
        return base - min(bonus, base - 1)


# ── Module-level convenience ────────────────────────────────────

_learner: RecoveryLearner | None = None


def get_learner() -> RecoveryLearner:
    global _learner
    if _learner is None:
        _learner = RecoveryLearner()
    return _learner


def scan_and_learn(workspace_id: str = "") -> LearnResult:
    """Convenience: scan ledger and learn new rules."""
    learner = get_learner()
    from .self_healer import get_healer
    healer = get_healer()
    learner.set_rule_engine(healer._rule_engine)
    if healer.ledger._db:
        learner.set_database(healer.ledger._db)
    return learner.scan_and_learn(workspace_id)
