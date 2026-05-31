"""
Auto Resolver — 冲突自动修复引擎

策略:
  FACT_CONFLICT     → HIGH_CONFIDENCE_PICK: 取高置信度 Agent 的值
  DEPENDENCY_BREAK  → RE_TRIGGER_UPSTREAM: 返回 re-trigger hint
  FORMAT_MISMATCH   → AUTO_TYPE_CONVERT: 简单类型转换 (str→int 等)

设计:
  - 非破坏性: 返回 Resolution 对象，调用方决定是否 apply
  - 每次尝试都 log 到 AuditReporter
  - 可配置置信度阈值 (min_confidence)
  - 不支持的冲突类型 → SKIPPED

用法:
  resolver = AutoResolver()
  resolutions = resolver.resolve(conflicts, step_outputs)
  for r in resolutions:
      if r.status == ResolutionStatus.RESOLVED:
          apply(r)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from .conflict_detector import Conflict, ConflictType, Severity


# ── Enums ───────────────────────────────────────────────────────

class ResolutionStrategy(Enum):
    HIGH_CONFIDENCE_PICK = "high_confidence_pick"
    RE_TRIGGER_UPSTREAM = "re_trigger_upstream"
    AUTO_TYPE_CONVERT = "auto_type_convert"


class ResolutionStatus(Enum):
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    SKIPPED = "skipped"


# ── Data classes ────────────────────────────────────────────────

@dataclass
class Resolution:
    """一次冲突解决结果"""
    conflict_type: ConflictType
    strategy: ResolutionStrategy
    status: ResolutionStatus
    original_agents: list[str]
    resolution_detail: str
    overridden_value: str | None = None
    confidence: float = 0.0
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "conflict_type": self.conflict_type.value,
            "strategy": self.strategy.value,
            "status": self.status.value,
            "agents": self.original_agents,
            "detail": self.resolution_detail,
            "overridden_value": self.overridden_value,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


# ── Auto Resolver ───────────────────────────────────────────────

@dataclass
class AutoResolver:
    """冲突自动修复器。

    调用 resolve() 传入 ConflictDetector.check() 的结果和 step_outputs，
    返回 Resolution 列表。调用方决定是否 apply。
    """

    min_confidence: float = 0.7

    def resolve(
        self,
        conflicts: list[Conflict],
        step_outputs: dict,
    ) -> list[Resolution]:
        """对冲突列表尝试自动修复。"""
        resolutions: list[Resolution] = []
        for conflict in conflicts:
            if conflict.conflict_type == ConflictType.FACT_CONFLICT:
                resolutions.append(self._resolve_fact_conflict(conflict, step_outputs))
            elif conflict.conflict_type == ConflictType.DEPENDENCY_BREAK:
                resolutions.append(self._resolve_dependency_break(conflict, step_outputs))
            elif conflict.conflict_type == ConflictType.FORMAT_MISMATCH:
                resolutions.append(self._resolve_format_mismatch(conflict, step_outputs))
            else:
                resolutions.append(Resolution(
                    conflict_type=conflict.conflict_type,
                    strategy=ResolutionStrategy.HIGH_CONFIDENCE_PICK,
                    status=ResolutionStatus.SKIPPED,
                    original_agents=conflict.agents_involved,
                    resolution_detail=f"不支持自动修复 {conflict.conflict_type.value} 类型",
                ))
        return resolutions

    # ── Fact conflict → HIGH_CONFIDENCE_PICK ────────────────────

    def _resolve_fact_conflict(
        self, conflict: Conflict, step_outputs: dict,
    ) -> Resolution:
        """取高置信度 Agent 的值。"""
        agents = conflict.agents_involved
        if len(agents) < 2:
            return self._escalate(conflict, "参与 Agent 不足 2 个")

        # Extract confidence scores from step outputs
        confidences: dict[str, float] = {}
        for agent in agents:
            output = step_outputs.get(agent)
            if output is None:
                continue
            out = getattr(output, "output", output)
            if isinstance(out, dict):
                conf = self._extract_confidence(out)
                if conf is not None:
                    confidences[agent] = conf

        if len(confidences) < 2:
            return self._escalate(conflict, "无法提取双方置信度，需要人工复核")

        # Pick highest confidence agent
        sorted_agents = sorted(confidences.items(), key=lambda x: x[1], reverse=True)
        high_agent, high_conf = sorted_agents[0]
        low_agent, low_conf = sorted_agents[1]

        # Check if confidence difference is significant enough
        if high_conf < self.min_confidence:
            return self._escalate(
                conflict,
                f"最高置信度 {high_conf:.0%} 低于阈值 {self.min_confidence:.0%}，需要人工复核",
            )

        # Get the winning value
        winning_output = step_outputs.get(high_agent)
        winning_out = getattr(winning_output, "output", winning_output)
        attr = conflict.evidence.get("attribute", "unknown")
        winning_value = None
        if isinstance(winning_out, dict):
            winning_value = winning_out.get(attr, str(winning_out))

        return Resolution(
            conflict_type=ConflictType.FACT_CONFLICT,
            strategy=ResolutionStrategy.HIGH_CONFIDENCE_PICK,
            status=ResolutionStatus.RESOLVED,
            original_agents=agents,
            resolution_detail=(
                f"采用 {high_agent} 的值 (置信度 {high_conf:.0%})，"
                f"覆盖 {low_agent} (置信度 {low_conf:.0%})"
            ),
            overridden_value=str(winning_value) if winning_value else None,
            confidence=high_conf,
            evidence={
                "winning_agent": high_agent,
                "losing_agent": low_agent,
                "winning_confidence": high_conf,
                "losing_confidence": low_conf,
                "attribute": attr,
            },
        )

    # ── Dependency break → RE_TRIGGER_UPSTREAM ──────────────────

    def _resolve_dependency_break(
        self, conflict: Conflict, step_outputs: dict,
    ) -> Resolution:
        """提取缺失字段，生成 re-trigger hint。"""
        missing_fields = conflict.evidence.get("missing_fields", [])
        agents = conflict.agents_involved

        if not missing_fields:
            return self._escalate(conflict, "无法确定缺失字段")

        upstream_agent = agents[0] if len(agents) > 0 else "unknown"

        return Resolution(
            conflict_type=ConflictType.DEPENDENCY_BREAK,
            strategy=ResolutionStrategy.RE_TRIGGER_UPSTREAM,
            status=ResolutionStatus.RESOLVED,
            original_agents=agents,
            resolution_detail=(
                f"需要重跑 {upstream_agent}，"
                f"确保输出包含字段: {', '.join(missing_fields)}"
            ),
            confidence=0.9,
            evidence={
                "upstream_agent": upstream_agent,
                "missing_fields": missing_fields,
                "re_trigger_hint": {
                    "agent": upstream_agent,
                    "required_fields": missing_fields,
                    "reason": f"下游依赖字段 {', '.join(missing_fields)} 缺失",
                },
            },
        )

    # ── Format mismatch → AUTO_TYPE_CONVERT ─────────────────────

    def _resolve_format_mismatch(
        self, conflict: Conflict, step_outputs: dict,
    ) -> Resolution:
        """尝试简单类型转换。"""
        agents = conflict.agents_involved
        field_name = conflict.evidence.get("field", "")
        expected_type = conflict.evidence.get("expected", "")
        actual_type = conflict.evidence.get("actual", "")

        if not field_name or not expected_type:
            return self._escalate(conflict, "缺少字段名或期望类型信息")

        # Get the upstream output
        upstream_agent = agents[0] if agents else None
        if upstream_agent is None:
            return self._escalate(conflict, "无上游 Agent")

        upstream_output = step_outputs.get(upstream_agent)
        upstream_out = getattr(upstream_output, "output", upstream_output)
        if not isinstance(upstream_out, dict) or field_name not in upstream_out:
            return self._escalate(conflict, f"上游输出中找不到字段 {field_name}")

        raw_value = upstream_out[field_name]

        # Try safe conversions
        converted, success = self._try_convert(raw_value, expected_type)
        if success:
            return Resolution(
                conflict_type=ConflictType.FORMAT_MISMATCH,
                strategy=ResolutionStrategy.AUTO_TYPE_CONVERT,
                status=ResolutionStatus.RESOLVED,
                original_agents=agents,
                resolution_detail=(
                    f"字段 '{field_name}' 自动转换: "
                    f"{actual_type}({raw_value!r}) → {expected_type}({converted!r})"
                ),
                overridden_value=str(converted),
                confidence=0.95,
                evidence={
                    "field": field_name,
                    "original_value": raw_value,
                    "original_type": actual_type,
                    "converted_value": converted,
                    "expected_type": expected_type,
                },
            )

        return self._escalate(
            conflict,
            f"无法安全转换 '{field_name}' 从 {actual_type} 到 {expected_type}",
        )

    # ── Helpers ─────────────────────────────────────────────────

    def _escalate(self, conflict: Conflict, reason: str) -> Resolution:
        """无法自动解决，升级到人工。"""
        return Resolution(
            conflict_type=conflict.conflict_type,
            strategy=ResolutionStrategy.HIGH_CONFIDENCE_PICK,
            status=ResolutionStatus.ESCALATED,
            original_agents=conflict.agents_involved,
            resolution_detail=f"升级到人工复核: {reason}",
            confidence=0.0,
            evidence={"escalation_reason": reason},
        )

    @staticmethod
    def _extract_confidence(output: dict) -> float | None:
        """从输出中提取置信度。"""
        for key in ("confidence", "confidence_score", "置信度", "score"):
            v = output.get(key)
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                try:
                    return float(v.replace("%", "")) / (100 if "%" in v else 1)
                except ValueError:
                    pass
        return None

    @staticmethod
    def _try_convert(value, target_type: str) -> tuple[object, bool]:
        """尝试安全的类型转换。返回 (converted_value, success)。"""
        converters = {
            "string": (str, True),
            "integer": (int, True),
            "number": (float, True),
            "boolean": (bool, True),
        }
        if target_type not in converters:
            return None, False

        converter, _ = converters[target_type]
        try:
            # Only allow safe conversions
            if target_type == "integer":
                if isinstance(value, str):
                    return int(float(value)), True
                return int(value), True
            elif target_type == "number":
                return float(value), True
            elif target_type == "string":
                return str(value), True
            elif target_type == "boolean":
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes"), True
                return bool(value), True
        except (ValueError, TypeError, OverflowError):
            pass
        return None, False


# ── Module-level convenience ────────────────────────────────────

_resolver: AutoResolver | None = None


def get_resolver() -> AutoResolver:
    global _resolver
    if _resolver is None:
        _resolver = AutoResolver()
    return _resolver


def auto_resolve(
    conflicts: list[Conflict],
    step_outputs: dict,
) -> list[Resolution]:
    """便捷函数: 自动解决冲突。"""
    return get_resolver().resolve(conflicts, step_outputs)
