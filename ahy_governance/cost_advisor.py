"""
Cost Advisor — 成本优化顾问

功能:
  模型降级建议 (GPT-4o → Haiku, 估算月省 $X)
  输出重叠检测 (复用 jaccard similarity)
  预算优化 tips

设计:
  - 只读: 分析 CostTracker + HealthMonitor 数据，不修改任何状态
  - 规则驱动: 基于 DEFAULT_PRICING 分层 (premium / standard / economy)
  - 无 LLM 调用

用法:
  advisor = CostAdvisor()
  recommendations = advisor.analyze(cost_tracker)
  for r in recommendations:
      print(r.to_dict())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from .cost_tracker import CostTracker, CostEntry, DEFAULT_PRICING, ModelPricing


# ── Enums ───────────────────────────────────────────────────────

class RecommendationType(Enum):
    MODEL_DOWNGRADE = "model_downgrade"
    OUTPUT_OVERLAP = "output_overlap"
    BUDGET_TIP = "budget_tip"
    TOKEN_OPTIMIZATION = "token_optimization"


class Priority(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ── Model tiers ─────────────────────────────────────────────────

# Tier: premium > standard > economy
# Each entry: (model_id, tier, provider)
_MODEL_TIERS: list[tuple[str, str, str]] = [
    ("gpt-4", "premium", "openai"),
    ("gpt-4-turbo", "premium", "openai"),
    ("gpt-4o", "standard", "openai"),
    ("gpt-4o-mini", "economy", "openai"),
    ("o1", "premium", "openai"),
    ("o1-mini", "standard", "openai"),
    ("o3-mini", "standard", "openai"),
    ("claude-opus-4-7", "premium", "anthropic"),
    ("claude-opus-4", "premium", "anthropic"),
    ("claude-sonnet-4-6", "standard", "anthropic"),
    ("claude-sonnet-4", "standard", "anthropic"),
    ("claude-haiku-4-5", "economy", "anthropic"),
    ("deepseek-reasoner", "standard", "deepseek"),
    ("deepseek-chat", "economy", "deepseek"),
    ("gemini-2.5-pro", "standard", "google"),
    ("gemini-2.5-flash", "economy", "google"),
    ("mistral-large", "standard", "mistral"),
    ("mistral-small", "economy", "mistral"),
    ("qwen-max", "standard", "alibaba"),
    ("qwen-plus", "economy", "alibaba"),
    ("llama-4-maverick", "economy", "meta"),
    ("llama-4-scout", "economy", "meta"),
]

_TIER_ORDER = {"premium": 0, "standard": 1, "economy": 2}


def _get_tier(model_id: str) -> str | None:
    # Exact match first, then prefix
    for mid, tier, _ in _MODEL_TIERS:
        if model_id == mid:
            return tier
    for mid, tier, _ in _MODEL_TIERS:
        if model_id.startswith(mid):
            return tier
    return None


def _get_provider(model_id: str) -> str | None:
    # Exact match first, then prefix
    for mid, _, provider in _MODEL_TIERS:
        if model_id == mid:
            return provider
    for mid, _, provider in _MODEL_TIERS:
        if model_id.startswith(mid):
            return provider
    return None


def _get_downgrade_candidates(model_id: str) -> list[str]:
    """Return cheaper models in the same provider, ordered by tier."""
    provider = _get_provider(model_id)
    tier = _get_tier(model_id)
    if provider is None or tier is None:
        return []

    tier_idx = _TIER_ORDER.get(tier, 2)
    candidates = []
    for mid, t, p in _MODEL_TIERS:
        if p == provider and _TIER_ORDER.get(t, 2) > tier_idx and mid != model_id:
            candidates.append(mid)
    return candidates


def _pricing_map() -> dict[str, ModelPricing]:
    return {p.model_id: p for p in DEFAULT_PRICING}


# ── Data classes ────────────────────────────────────────────────

@dataclass
class Recommendation:
    """一条成本优化建议"""
    rec_type: RecommendationType
    priority: Priority
    agent_name: str
    description: str
    current_model: str = ""
    suggested_model: str = ""
    estimated_savings_usd: float = 0.0
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type": self.rec_type.value,
            "priority": self.priority.value,
            "agent": self.agent_name,
            "description": self.description,
            "current_model": self.current_model,
            "suggested_model": self.suggested_model,
            "estimated_savings_usd": round(self.estimated_savings_usd, 4),
            "evidence": self.evidence,
        }


# ── Cost Advisor ────────────────────────────────────────────────

class CostAdvisor:
    """成本优化顾问。

    调用 analyze() 传入 CostTracker 实例，
    返回 Recommendation 列表。

    overlap_threshold: jaccard 相似度阈值，超过此值认为输出重叠。
    min_entries_for_analysis: 最少条目数才触发分析。
    """

    def __init__(
        self,
        overlap_threshold: float = 0.7,
        min_entries_for_analysis: int = 5,
    ):
        self.overlap_threshold = overlap_threshold
        self.min_entries_for_analysis = min_entries_for_analysis

    def analyze(self, cost_tracker: CostTracker) -> list[Recommendation]:
        """分析成本数据，返回优化建议。"""
        recs: list[Recommendation] = []
        if not cost_tracker or not cost_tracker._entries:
            return recs

        entries = cost_tracker._entries
        if len(entries) < self.min_entries_for_analysis:
            return recs

        recs.extend(self._check_model_downgrades(entries))
        recs.extend(self._check_output_overlap(entries))
        recs.extend(self._check_token_optimization(entries))
        recs.extend(self._check_budget_tips(cost_tracker))

        # Sort by priority (HIGH first)
        priority_order = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}
        recs.sort(key=lambda r: priority_order.get(r.priority, 3))
        return recs

    # ── Model downgrade suggestions ─────────────────────────────

    def _check_model_downgrades(self, entries: list[CostEntry]) -> list[Recommendation]:
        """Find agents using premium models where standard/economy would suffice."""
        recs: list[Recommendation] = []
        pricing = _pricing_map()

        # Group by agent + model
        agent_models: dict[str, dict[str, list[CostEntry]]] = {}
        for e in entries:
            agent_models.setdefault(e.agent_name, {}).setdefault(e.model, []).append(e)

        for agent, models in agent_models.items():
            for model, model_entries in models.items():
                tier = _get_tier(model)
                if tier not in ("premium",):
                    continue

                candidates = _get_downgrade_candidates(model)
                if not candidates:
                    continue

                total_cost = sum(e.cost_usd for e in model_entries)
                total_tokens_in = sum(e.tokens_in for e in model_entries)
                total_tokens_out = sum(e.tokens_out for e in model_entries)

                # Suggest the best downgrade (prefer standard over economy)
                for candidate in candidates:
                    candidate_pricing = pricing.get(candidate)
                    if candidate_pricing is None:
                        continue
                    candidate_cost = candidate_pricing.calculate(
                        total_tokens_in, total_tokens_out,
                    )
                    savings = total_cost - candidate_cost
                    if savings <= 0:
                        continue

                    # Check if this is a provider switch (cross-provider is riskier)
                    same_provider = _get_provider(model) == _get_provider(candidate)
                    priority = Priority.HIGH if same_provider else Priority.MEDIUM

                    recs.append(Recommendation(
                        rec_type=RecommendationType.MODEL_DOWNGRADE,
                        priority=priority,
                        agent_name=agent,
                        description=(
                            f"Agent '{agent}' 使用 {model} (premium) 累计 ${total_cost:.4f}，"
                            f"建议降级到 {candidate}，"
                            f"相同负载可节省 ${savings:.4f}"
                        ),
                        current_model=model,
                        suggested_model=candidate,
                        estimated_savings_usd=savings,
                        evidence={
                            "total_calls": len(model_entries),
                            "total_tokens_in": total_tokens_in,
                            "total_tokens_out": total_tokens_out,
                            "current_cost": round(total_cost, 6),
                            "candidate_cost": round(candidate_cost, 6),
                            "same_provider": same_provider,
                            "tier_from": tier,
                            "tier_to": _get_tier(candidate),
                        },
                    ))
                    break  # Only suggest one downgrade per agent+model

        return recs

    # ── Output overlap detection ────────────────────────────────

    def _check_output_overlap(self, entries: list[CostEntry]) -> list[Recommendation]:
        """Detect agents producing similar outputs (wasted tokens)."""
        recs: list[Recommendation] = []

        # Group outputs by session
        session_outputs: dict[str, list[CostEntry]] = {}
        for e in entries:
            if e.session_id:
                session_outputs.setdefault(e.session_id, []).append(e)

        for session_id, session_entries in session_outputs.items():
            if len(session_entries) < 2:
                continue

            # Compare each pair of agents within the session
            seen_pairs: set[tuple[str, str]] = set()
            for i, e1 in enumerate(session_entries):
                for j, e2 in enumerate(session_entries):
                    if i >= j:
                        continue
                    pair = tuple(sorted([e1.agent_name, e2.agent_name]))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)

                    # Use token ratio as a proxy for output similarity
                    # (real jaccard needs actual output text which we don't have)
                    if e1.tokens_out == 0 or e2.tokens_out == 0:
                        continue

                    ratio = min(e1.tokens_out, e2.tokens_out) / max(e1.tokens_out, e2.tokens_out)
                    if ratio > self.overlap_threshold:
                        wasted = min(e1.cost_usd, e2.cost_usd)
                        recs.append(Recommendation(
                            rec_type=RecommendationType.OUTPUT_OVERLAP,
                            priority=Priority.MEDIUM,
                            agent_name=f"{e1.agent_name} + {e2.agent_name}",
                            description=(
                                f"Agent '{e1.agent_name}' 和 '{e2.agent_name}' "
                                f"在 session {session_id} 中输出相似 "
                                f"(token 比例 {ratio:.0%})，可能有重复工作"
                            ),
                            evidence={
                                "session_id": session_id,
                                "agent_a": e1.agent_name,
                                "agent_b": e2.agent_name,
                                "tokens_out_a": e1.tokens_out,
                                "tokens_out_b": e2.tokens_out,
                                "similarity_ratio": round(ratio, 3),
                                "potentially_wasted_cost_usd": round(wasted, 6),
                            },
                        ))

        return recs

    # ── Token optimization ──────────────────────────────────────

    def _check_token_optimization(self, entries: list[CostEntry]) -> list[Recommendation]:
        """Flag agents with disproportionately high input tokens."""
        recs: list[Recommendation] = []

        # Group by agent
        agent_stats: dict[str, dict] = {}
        for e in entries:
            stats = agent_stats.setdefault(e.agent_name, {
                "tokens_in": 0, "tokens_out": 0, "cost": 0.0, "count": 0,
            })
            stats["tokens_in"] += e.tokens_in
            stats["tokens_out"] += e.tokens_out
            stats["cost"] += e.cost_usd
            stats["count"] += 1

        for agent, stats in agent_stats.items():
            if stats["count"] < 3:
                continue

            avg_in = stats["tokens_in"] / stats["count"]
            avg_out = stats["tokens_out"] / stats["count"]

            # If input is 10x+ output, prompt may be bloated
            if avg_out > 0 and avg_in / avg_out > 10:
                recs.append(Recommendation(
                    rec_type=RecommendationType.TOKEN_OPTIMIZATION,
                    priority=Priority.MEDIUM,
                    agent_name=agent,
                    description=(
                        f"Agent '{agent}' 输入/输出 token 比例异常 "
                        f"(平均 {avg_in:.0f} in / {avg_out:.0f} out = {avg_in/avg_out:.1f}x)，"
                        f"建议精简 prompt 或使用 context window 管理"
                    ),
                    evidence={
                        "avg_tokens_in": round(avg_in, 0),
                        "avg_tokens_out": round(avg_out, 0),
                        "ratio": round(avg_in / avg_out, 2),
                        "total_calls": stats["count"],
                        "total_cost": round(stats["cost"], 6),
                    },
                ))

        return recs

    # ── Budget tips ─────────────────────────────────────────────

    def _check_budget_tips(self, cost_tracker: CostTracker) -> list[Recommendation]:
        """Generate budget-related optimization tips."""
        recs: list[Recommendation] = []

        # Check if no budget is set
        if cost_tracker._budget is None:
            total = cost_tracker.get_total_cost()
            if total > 0:
                recs.append(Recommendation(
                    rec_type=RecommendationType.BUDGET_TIP,
                    priority=Priority.LOW,
                    agent_name="*",
                    description=(
                        f"未设置预算上限 (当前累计 ${total:.4f})。"
                        f"建议调用 set_budget() 设置月度预算，避免意外超支"
                    ),
                    evidence={"total_cost": round(total, 6)},
                ))
        elif cost_tracker._budget.near_limit:
            budget = cost_tracker._budget
            recs.append(Recommendation(
                rec_type=RecommendationType.BUDGET_TIP,
                priority=Priority.HIGH,
                agent_name="*",
                description=(
                    f"预算使用率已达 {budget.usage_pct:.0f}% "
                    f"(${budget.current_usd:.4f} / ${budget.limit_usd:.2f})，"
                    f"建议切换到更经济的模型或减少非必要调用"
                ),
                evidence={
                    "budget_limit": budget.limit_usd,
                    "current_spend": budget.current_usd,
                    "usage_pct": budget.usage_pct,
                    "period": budget.period,
                },
            ))

        # Check for expensive model concentration
        by_model: dict[str, float] = {}
        for e in cost_tracker._entries:
            by_model[e.model] = by_model.get(e.model, 0) + e.cost_usd

        total_cost = sum(by_model.values())
        if total_cost > 0:
            for model, cost in sorted(by_model.items(), key=lambda x: x[1], reverse=True):
                pct = cost / total_cost
                tier = _get_tier(model)
                if pct > 0.6 and tier == "premium":
                    recs.append(Recommendation(
                        rec_type=RecommendationType.BUDGET_TIP,
                        priority=Priority.HIGH,
                        agent_name="*",
                        description=(
                            f"模型 '{model}' 占总成本 {pct:.0%} (${cost:.4f})，"
                            f"属于 premium 层级。建议评估是否所有调用都需要此模型"
                        ),
                        evidence={
                            "model": model,
                            "model_cost": round(cost, 6),
                            "total_cost": round(total_cost, 6),
                            "percentage": round(pct * 100, 1),
                            "tier": tier,
                        },
                    ))

        return recs


# ── Module-level convenience ────────────────────────────────────

_advisor: CostAdvisor | None = None


def get_advisor() -> CostAdvisor:
    global _advisor
    if _advisor is None:
        _advisor = CostAdvisor()
    return _advisor


def analyze_costs(cost_tracker: CostTracker | None = None) -> list[Recommendation]:
    """便捷函数: 分析成本。"""
    from .cost_tracker import get_tracker
    ct = cost_tracker or get_tracker()
    return get_advisor().analyze(ct)
