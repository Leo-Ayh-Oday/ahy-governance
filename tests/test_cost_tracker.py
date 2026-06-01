"""Cost Tracker 测试 — 定价/追踪/预算/导出"""

import json
import os
import tempfile

import pytest

from ahy_governance import (
    CostTracker,
    CostEntry,
    BudgetConfig,
    BudgetExceededError,
    ModelPricing,
    track_cost,
    get_tracker,
)


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def tracker():
    t = CostTracker()
    yield t
    t.reset()


@pytest.fixture
def populated_tracker(tracker):
    tracker.track("Planner", "claude-sonnet-4-6", 15000, 3000, session_id="sess-1")
    tracker.track("Executor", "gpt-4o", 8000, 2000, session_id="sess-1")
    tracker.track("Reviewer", "claude-haiku-4-5", 5000, 500, session_id="sess-2")
    tracker.track("Planner", "deepseek-chat", 10000, 5000, session_id="sess-2")
    return tracker


# ── Pricing Tests ───────────────────────────────────────────────

class TestPricing:
    def test_calculate_cost(self):
        p = ModelPricing("test-model", "test", 10.0, 20.0)
        cost = p.calculate(50000, 30000)
        assert cost == pytest.approx(0.5 + 0.6, rel=0.01)

    def test_zero_tokens(self):
        p = ModelPricing("test", "test", 10.0, 20.0)
        assert p.calculate(0, 0) == 0.0

    def test_lookup_known_model(self, tracker):
        p = tracker.get_pricing("gpt-4o")
        assert p is not None
        assert p.provider == "openai"
        assert p.input_price_per_1m == 2.50

    def test_lookup_unknown_model(self, tracker):
        assert tracker.get_pricing("nonexistent-model-v999") is None

    def test_register_custom_pricing(self, tracker):
        tracker.register_pricing("custom-model", 5.0, 10.0, provider="custom-co")
        p = tracker.get_pricing("custom-model")
        assert p is not None
        assert p.input_price_per_1m == 5.0

    def test_estimate_cost(self, tracker):
        cost = tracker.estimate("gpt-4o-mini", 100000, 50000)
        # 100K in * 0.15/1M = 0.015, 50K out * 0.60/1M = 0.03, total ≈ 0.045
        assert cost == pytest.approx(0.045, rel=0.01)

    def test_estimate_unknown_model_raises(self, tracker):
        with pytest.raises(KeyError, match="Unknown model"):
            tracker.estimate("no-such-model", 100, 100)

    def test_prefix_match(self, tracker):
        """Prefix matching supports variant IDs like claude-sonnet-4-6-20250501"""
        tracker.register_pricing("claude-sonnet-4-6", 3.0, 15.0)
        p = tracker.get_pricing("claude-sonnet-4-6-20250501")
        # The model_id "claude-sonnet-4-6" is a prefix of the lookup
        assert p is not None

    def test_all_default_models_have_pricing(self, tracker):
        from ahy_governance.cost_tracker import DEFAULT_PRICING
        assert len(DEFAULT_PRICING) >= 20
        for mp in DEFAULT_PRICING:
            assert tracker.get_pricing(mp.model_id) is not None


# ── Tracking Tests ──────────────────────────────────────────────

class TestTracking:
    def test_track_returns_entry(self, tracker):
        entry = tracker.track("Analyst", "gpt-4o", 1000, 500)
        assert isinstance(entry, CostEntry)
        assert entry.agent_name == "Analyst"
        assert entry.model == "gpt-4o"
        assert entry.tokens_in == 1000
        assert entry.tokens_out == 500
        assert entry.cost_usd > 0

    def test_track_unknown_model_defaults(self, tracker):
        entry = tracker.track("X", "fake-model-999", 100, 100)
        assert entry.cost_usd > 0
        assert entry.warning is not None
        assert "fake-model-999" in entry.warning

    def test_entry_count(self, populated_tracker):
        assert populated_tracker.entry_count == 4

    def test_track_preserves_timestamp(self, tracker):
        entry = tracker.track("A", "gpt-4o-mini", 100, 100)
        assert "T" in entry.timestamp
        assert entry.timestamp.endswith("+00:00") or "Z" in entry.timestamp

    def test_entry_to_dict(self, tracker):
        entry = tracker.track("A", "gpt-4o-mini", 500, 300, session_id="s1")
        d = entry.to_dict()
        assert d["agent"] == "A"
        assert d["tokens_total"] == 800
        assert d["session_id"] == "s1"


# ── Cost Aggregation Tests ──────────────────────────────────────

class TestCostAggregation:
    def test_total_cost(self, populated_tracker):
        total = populated_tracker.get_total_cost()
        assert total > 0
        assert total == sum(e.cost_usd for e in populated_tracker._entries)

    def test_agent_cost(self, populated_tracker):
        planner_cost = populated_tracker.get_agent_cost("Planner")
        assert planner_cost > 0

    def test_agent_cost_zero_for_unknown(self, populated_tracker):
        assert populated_tracker.get_agent_cost("NonExistentAgent") == 0.0

    def test_session_cost(self, populated_tracker):
        cost_s1 = populated_tracker.get_session_cost("sess-1")
        cost_s2 = populated_tracker.get_session_cost("sess-2")
        assert cost_s1 > 0
        assert cost_s2 > 0
        assert populated_tracker.get_session_cost("no-such-session") == 0.0

    def test_model_cost(self, populated_tracker):
        gpt_cost = populated_tracker.get_model_cost("gpt-4o")
        assert gpt_cost > 0

    def test_token_totals(self, populated_tracker):
        t = populated_tracker.get_token_totals()
        assert t["tokens_in"] > 0
        assert t["tokens_out"] > 0
        assert t["tokens_total"] == t["tokens_in"] + t["tokens_out"]


# ── Budget Tests ────────────────────────────────────────────────

class TestBudget:
    def test_set_budget(self, tracker):
        cfg = tracker.set_budget(100.0, period="monthly")
        assert cfg.limit_usd == 100.0
        assert cfg.period == "monthly"

    def test_check_budget_under_limit(self, tracker):
        tracker.set_budget(10.0)
        tracker.track("A", "gpt-4o-mini", 1000, 500)
        remaining = tracker.check_budget()
        assert remaining > 0

    def test_budget_exceeded_raises(self, tracker):
        tracker.set_budget(0.0001, auto_block=True)  # tiny budget
        with pytest.raises(BudgetExceededError):
            tracker.track("A", "gpt-4o", 50000, 50000)

    def test_budget_exceeded_error_attrs(self, tracker):
        tracker.set_budget(0.001, auto_block=True)
        try:
            tracker.track("A", "gpt-4o", 100000, 100000)
        except BudgetExceededError as e:
            assert "Budget exceeded" in str(e)
            assert e.limit == 0.001
            assert e.period == "monthly"

    def test_budget_no_auto_block(self, tracker):
        """With auto_block=False, tracking succeeds even over budget."""
        tracker.set_budget(0.0001, auto_block=False)
        entry = tracker.track("A", "gpt-4o", 50000, 50000)
        assert entry.cost_usd > 0
        # check_budget still reports remaining (negative)
        status = tracker.get_budget_status()
        assert status["remaining_usd"] < 0

    def test_no_budget_returns_inf(self, tracker):
        assert tracker.check_budget() == float("inf")

    def test_budget_status(self, tracker):
        tracker.set_budget(10.0, alert_threshold=0.5)
        status = tracker.get_budget_status()
        assert status["limit_usd"] == 10.0
        assert status["period"] == "monthly"
        assert not status["near_limit"]

    def test_near_limit_alert(self, tracker):
        tracker.set_budget(1.0, alert_threshold=0.5)
        # haiku-4-5: 2.5M in + 200K out ≈ $0.875, which is >80% of $1.00
        tracker.track("A", "claude-haiku-4-5", 2500000, 200000)
        status = tracker.get_budget_status()
        assert status["near_limit"]

    def test_reset_budget(self, tracker):
        tracker.set_budget(100.0)
        tracker.reset_budget()
        assert tracker.get_budget_status() is None

    def test_budget_usage_pct(self, tracker):
        tracker.set_budget(10.0)
        # Track ~$1 worth
        tracker.track("A", "gpt-4o-mini", 0, 1666000)  # ~$1
        status = tracker.get_budget_status()
        assert status["usage_pct"] > 0


# ── Report Tests ────────────────────────────────────────────────

class TestReport:
    def test_report_structure(self, populated_tracker):
        report = populated_tracker.get_report()
        assert "total_cost_usd" in report
        assert "by_agent" in report
        assert "by_session" in report
        assert "by_model" in report
        assert "tokens" in report
        assert "budget" in report  # None when no budget set

    def test_report_by_agent_sum(self, populated_tracker):
        report = populated_tracker.get_report()
        agent_sum = sum(report["by_agent"].values())
        assert agent_sum == pytest.approx(report["total_cost_usd"], rel=0.01)

    def test_report_empty(self, tracker):
        report = tracker.get_report()
        assert report["total_cost_usd"] == 0.0
        assert report["total_entries"] == 0


# ── Export Tests ────────────────────────────────────────────────

class TestExport:
    def test_export_csv(self, populated_tracker):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "costs.csv")
            populated_tracker.export_csv(path)
            assert os.path.exists(path)
            with open(path) as f:
                lines = f.readlines()
            assert len(lines) == 5  # header + 4 entries
            assert "agent,model,tokens_in" in lines[0]

    def test_export_json(self, populated_tracker):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "costs.json")
            populated_tracker.export_json(path)
            assert os.path.exists(path)
            with open(path) as f:
                data = json.load(f)
            assert len(data) == 4
            assert data[0]["agent"] == "Planner"

    def test_export_empty(self, tracker):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "empty.csv")
            tracker.export_csv(path)
            with open(path) as f:
                content = f.read()
            assert "agent,model" in content


# ── Edge Cases ──────────────────────────────────────────────────

class TestEdgeCases:
    def test_single_token(self, tracker):
        entry = tracker.track("A", "gpt-4o-mini", 1, 1)
        assert entry.cost_usd > 0
        assert entry.cost_usd < 0.01

    def test_large_token_count(self, tracker):
        # 1 billion tokens
        entry = tracker.track("BigAgent", "claude-haiku-4-5", 1_000_000_000, 0)
        assert entry.cost_usd > 0

    def test_reset_clears_all(self, populated_tracker):
        populated_tracker.set_budget(100.0)
        populated_tracker.reset()
        assert populated_tracker.entry_count == 0
        assert populated_tracker.get_total_cost() == 0.0
        assert populated_tracker.get_budget_status() is None

    def test_multiple_entries_same_agent(self, tracker):
        for _ in range(10):
            tracker.track("Worker", "gpt-4o-mini", 1000, 500)
        assert tracker.entry_count == 10
        cost = tracker.get_agent_cost("Worker")
        assert cost == pytest.approx(tracker.get_total_cost(), rel=0.01)


# ── Convenience Functions ───────────────────────────────────────

class TestConvenienceFunctions:
    def test_track_cost_global(self):
        """track_cost() uses the module-level singleton."""
        t = get_tracker()
        t.reset()
        entry = track_cost("GlobalAgent", "gpt-4o-mini", 500, 200)
        assert entry.agent_name == "GlobalAgent"
        assert t.entry_count == 1
        t.reset()

    def test_get_tracker_singleton(self):
        t1 = get_tracker()
        t2 = get_tracker()
        assert t1 is t2
        t1.reset()


# ── BudgetConfig Tests ──────────────────────────────────────────

class TestBudgetConfig:
    def test_remaining(self):
        cfg = BudgetConfig(limit_usd=100.0, current_usd=30.0)
        assert cfg.remaining == 70.0

    def test_usage_pct(self):
        cfg = BudgetConfig(limit_usd=100.0, current_usd=45.0)
        assert cfg.usage_pct == 45.0

    def test_near_limit_true(self):
        cfg = BudgetConfig(limit_usd=100.0, current_usd=85.0, alert_threshold=0.8)
        assert cfg.near_limit

    def test_near_limit_false(self):
        cfg = BudgetConfig(limit_usd=100.0, current_usd=50.0, alert_threshold=0.8)
        assert not cfg.near_limit
