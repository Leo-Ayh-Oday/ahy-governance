"""Tests for Cost Advisor — 成本优化顾问."""

import pytest
from datetime import datetime, timezone, timedelta

from ahy_governance.cost_advisor import (
    CostAdvisor,
    Recommendation,
    RecommendationType,
    Priority,
    get_advisor,
    analyze_costs,
    _get_tier,
    _get_provider,
    _get_downgrade_candidates,
)
from ahy_governance.cost_tracker import CostTracker, CostEntry, BudgetConfig


# ── Helpers ─────────────────────────────────────────────────────

def _entry(
    agent="Planner", model="gpt-4o", tokens_in=1000,
    tokens_out=500, cost=0.01, session="s1", minutes_ago=0,
) -> CostEntry:
    ts = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
    return CostEntry(agent, model, tokens_in, tokens_out, cost, session, ts)


def _make_tracker(entries: list[CostEntry]) -> CostTracker:
    ct = CostTracker()
    ct._entries = entries
    return ct


# ── Tier helpers ────────────────────────────────────────────────

class TestTierHelpers:
    def test_get_tier_known_models(self):
        assert _get_tier("gpt-4") == "premium"
        assert _get_tier("gpt-4o") == "standard"
        assert _get_tier("gpt-4o-mini") == "economy"
        assert _get_tier("claude-opus-4-7") == "premium"
        assert _get_tier("claude-sonnet-4-6") == "standard"
        assert _get_tier("claude-haiku-4-5") == "economy"

    def test_get_tier_unknown(self):
        assert _get_tier("unknown-model") is None

    def test_get_provider_known(self):
        assert _get_provider("gpt-4o") == "openai"
        assert _get_provider("claude-sonnet-4-6") == "anthropic"
        assert _get_provider("deepseek-chat") == "deepseek"

    def test_get_provider_unknown(self):
        assert _get_provider("unknown-model") is None

    def test_downgrade_candidates_premium(self):
        cands = _get_downgrade_candidates("gpt-4")
        assert "gpt-4o" in cands
        assert "gpt-4o-mini" in cands

    def test_downgrade_candidates_standard(self):
        cands = _get_downgrade_candidates("gpt-4o")
        assert "gpt-4o-mini" in cands
        assert "gpt-4" not in cands

    def test_downgrade_candidates_economy(self):
        cands = _get_downgrade_candidates("gpt-4o-mini")
        assert cands == []

    def test_downgrade_candidates_same_provider(self):
        cands = _get_downgrade_candidates("claude-opus-4-7")
        assert "claude-sonnet-4-6" in cands
        assert "claude-haiku-4-5" in cands


# ── Model downgrade detection ───────────────────────────────────

class TestModelDowngrade:
    def test_premium_model_suggests_downgrade(self):
        entries = [_entry(model="gpt-4", tokens_in=5000, tokens_out=2000, cost=0.3)
                   for _ in range(10)]
        ct = _make_tracker(entries)
        advisor = CostAdvisor(min_entries_for_analysis=1)
        recs = advisor.analyze(ct)

        downgrade_recs = [r for r in recs if r.rec_type == RecommendationType.MODEL_DOWNGRADE]
        assert len(downgrade_recs) >= 1
        r = downgrade_recs[0]
        assert r.current_model == "gpt-4"
        assert r.suggested_model in ("gpt-4o", "gpt-4o-mini")
        assert r.estimated_savings_usd > 0

    def test_standard_model_no_downgrade(self):
        """Standard tier models should not trigger downgrade suggestions."""
        entries = [_entry(model="gpt-4o", tokens_in=5000, tokens_out=2000, cost=0.05)
                   for _ in range(10)]
        ct = _make_tracker(entries)
        advisor = CostAdvisor(min_entries_for_analysis=1)
        recs = advisor.analyze(ct)

        downgrade_recs = [r for r in recs if r.rec_type == RecommendationType.MODEL_DOWNGRADE]
        assert len(downgrade_recs) == 0

    def test_economy_model_no_downgrade(self):
        entries = [_entry(model="gpt-4o-mini", tokens_in=5000, tokens_out=2000, cost=0.005)
                   for _ in range(10)]
        ct = _make_tracker(entries)
        advisor = CostAdvisor(min_entries_for_analysis=1)
        recs = advisor.analyze(ct)

        downgrade_recs = [r for r in recs if r.rec_type == RecommendationType.MODEL_DOWNGRADE]
        assert len(downgrade_recs) == 0


# ── Output overlap detection ────────────────────────────────────

class TestOutputOverlap:
    def test_similar_tokens_detected(self):
        """Two agents with very similar output tokens should be flagged."""
        entries = [
            _entry(agent="A", tokens_out=1000, session="s1"),
            _entry(agent="B", tokens_out=950, session="s1"),
        ]
        ct = _make_tracker(entries)
        advisor = CostAdvisor(min_entries_for_analysis=1, overlap_threshold=0.7)
        recs = advisor.analyze(ct)

        overlap_recs = [r for r in recs if r.rec_type == RecommendationType.OUTPUT_OVERLAP]
        assert len(overlap_recs) == 1
        assert "A" in overlap_recs[0].agent_name
        assert "B" in overlap_recs[0].agent_name

    def test_different_tokens_no_overlap(self):
        entries = [
            _entry(agent="A", tokens_out=1000, session="s1"),
            _entry(agent="B", tokens_out=100, session="s1"),
        ]
        ct = _make_tracker(entries)
        advisor = CostAdvisor(min_entries_for_analysis=1, overlap_threshold=0.7)
        recs = advisor.analyze(ct)

        overlap_recs = [r for r in recs if r.rec_type == RecommendationType.OUTPUT_OVERLAP]
        assert len(overlap_recs) == 0

    def test_no_session_skipped(self):
        """Entries without session_id should not be checked for overlap."""
        entries = [
            _entry(agent="A", tokens_out=1000, session=""),
            _entry(agent="B", tokens_out=950, session=""),
        ]
        ct = _make_tracker(entries)
        advisor = CostAdvisor(min_entries_for_analysis=1)
        recs = advisor.analyze(ct)

        overlap_recs = [r for r in recs if r.rec_type == RecommendationType.OUTPUT_OVERLAP]
        assert len(overlap_recs) == 0


# ── Token optimization ──────────────────────────────────────────

class TestTokenOptimization:
    def test_high_input_ratio_flagged(self):
        """Agent with 10x+ input/output ratio should be flagged."""
        entries = [
            _entry(agent="Bloated", tokens_in=50000, tokens_out=500)
            for _ in range(5)
        ]
        ct = _make_tracker(entries)
        advisor = CostAdvisor(min_entries_for_analysis=1)
        recs = advisor.analyze(ct)

        token_recs = [r for r in recs if r.rec_type == RecommendationType.TOKEN_OPTIMIZATION]
        assert len(token_recs) == 1
        assert token_recs[0].agent_name == "Bloated"

    def test_normal_ratio_no_flag(self):
        entries = [
            _entry(agent="Normal", tokens_in=2000, tokens_out=1000)
            for _ in range(5)
        ]
        ct = _make_tracker(entries)
        advisor = CostAdvisor(min_entries_for_analysis=1)
        recs = advisor.analyze(ct)

        token_recs = [r for r in recs if r.rec_type == RecommendationType.TOKEN_OPTIMIZATION]
        assert len(token_recs) == 0

    def test_few_entries_skipped(self):
        entries = [_entry(agent="New", tokens_in=50000, tokens_out=500)]
        ct = _make_tracker(entries)
        advisor = CostAdvisor(min_entries_for_analysis=1)
        recs = advisor.analyze(ct)

        token_recs = [r for r in recs if r.rec_type == RecommendationType.TOKEN_OPTIMIZATION]
        assert len(token_recs) == 0


# ── Budget tips ─────────────────────────────────────────────────

class TestBudgetTips:
    def test_no_budget_tip(self):
        entries = [_entry() for _ in range(10)]
        ct = _make_tracker(entries)
        advisor = CostAdvisor(min_entries_for_analysis=1)
        recs = advisor.analyze(ct)

        budget_recs = [r for r in recs if r.rec_type == RecommendationType.BUDGET_TIP]
        assert len(budget_recs) >= 1
        assert "未设置预算" in budget_recs[0].description

    def test_near_budget_limit_tip(self):
        entries = [_entry() for _ in range(10)]
        ct = _make_tracker(entries)
        ct._budget = BudgetConfig(limit_usd=1.0, current_usd=0.9, period="monthly")
        advisor = CostAdvisor(min_entries_for_analysis=1)
        recs = advisor.analyze(ct)

        budget_recs = [r for r in recs if r.rec_type == RecommendationType.BUDGET_TIP
                       and "使用率" in r.description]
        assert len(budget_recs) == 1
        assert budget_recs[0].priority == Priority.HIGH

    def test_expensive_model_concentration(self):
        entries = [
            _entry(model="gpt-4", cost=0.5) for _ in range(10)
        ] + [
            _entry(model="gpt-4o-mini", cost=0.001) for _ in range(2)
        ]
        ct = _make_tracker(entries)
        ct._budget = BudgetConfig(limit_usd=100.0, current_usd=5.0)
        advisor = CostAdvisor(min_entries_for_analysis=1)
        recs = advisor.analyze(ct)

        concentration_recs = [r for r in recs
                              if r.rec_type == RecommendationType.BUDGET_TIP
                              and "占总成本" in r.description]
        assert len(concentration_recs) >= 1


# ── Edge cases ──────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_tracker(self):
        ct = _make_tracker([])
        advisor = CostAdvisor()
        assert advisor.analyze(ct) == []

    def test_none_tracker(self):
        advisor = CostAdvisor()
        # Should not crash
        ct = _make_tracker([])
        assert advisor.analyze(ct) == []

    def test_below_min_entries(self):
        entries = [_entry() for _ in range(3)]
        ct = _make_tracker(entries)
        advisor = CostAdvisor(min_entries_for_analysis=10)
        assert advisor.analyze(ct) == []

    def test_mixed_recommendations(self):
        """Multiple recommendation types can coexist."""
        entries = [
            _entry(agent="Premium", model="gpt-4", tokens_in=50000,
                   tokens_out=500, cost=0.5, session="s1")
            for _ in range(10)
        ] + [
            _entry(agent="Bloated", model="gpt-4o", tokens_in=50000,
                   tokens_out=500, cost=0.05, session="s1")
            for _ in range(5)
        ]
        ct = _make_tracker(entries)
        advisor = CostAdvisor(min_entries_for_analysis=1)
        recs = advisor.analyze(ct)

        types = {r.rec_type for r in recs}
        assert RecommendationType.MODEL_DOWNGRADE in types
        assert RecommendationType.TOKEN_OPTIMIZATION in types


# ── Recommendation dataclass ────────────────────────────────────

class TestRecommendation:
    def test_to_dict(self):
        r = Recommendation(
            rec_type=RecommendationType.MODEL_DOWNGRADE,
            priority=Priority.HIGH,
            agent_name="Planner",
            description="降级建议",
            current_model="gpt-4",
            suggested_model="gpt-4o",
            estimated_savings_usd=1.23,
        )
        d = r.to_dict()
        assert d["type"] == "model_downgrade"
        assert d["priority"] == "high"
        assert d["agent"] == "Planner"
        assert d["estimated_savings_usd"] == 1.23


# ── Singleton and convenience ──────────────────────────────────

class TestSingleton:
    def test_get_advisor_returns_singleton(self):
        a1 = get_advisor()
        a2 = get_advisor()
        assert a1 is a2

    def test_analyze_costs_convenience(self):
        result = analyze_costs()
        assert isinstance(result, list)
