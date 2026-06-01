"""
Cost Tracker — Agent 调用成本追踪与预算熔断

功能:
  Token → 金额换算（支持 20+ 模型实时定价）
  按 Agent / 会话 / 用户维度的成本归因
  预算上限 + 熔断机制

用法:
  tracker = CostTracker()
  tracker.track("Planner", "claude-sonnet-4-6", 15000, 3000, session_id="sess-001")
  remaining = tracker.check_budget()  # 超预算抛 BudgetExceededError
  report = tracker.get_report()       # 多维成本报告
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# ── Default pricing table (USD per 1M tokens) ──────────────────

@dataclass
class ModelPricing:
    model_id: str
    provider: str
    input_price_per_1m: float   # USD per 1M input tokens
    output_price_per_1m: float  # USD per 1M output tokens
    note: str = ""

    def calculate(self, tokens_in: int, tokens_out: int) -> float:
        in_cost = (tokens_in / 1_000_000) * self.input_price_per_1m
        out_cost = (tokens_out / 1_000_000) * self.output_price_per_1m
        return round(in_cost + out_cost, 6)


DEFAULT_PRICING: list[ModelPricing] = [
    # ── OpenAI ──
    ModelPricing("gpt-4o", "openai", 2.50, 10.00),
    ModelPricing("gpt-4o-mini", "openai", 0.15, 0.60),
    ModelPricing("gpt-4-turbo", "openai", 10.00, 30.00),
    ModelPricing("gpt-4", "openai", 30.00, 60.00),
    ModelPricing("o3-mini", "openai", 1.10, 4.40),
    ModelPricing("o1", "openai", 15.00, 60.00),
    ModelPricing("o1-mini", "openai", 3.00, 12.00),

    # ── Anthropic ──
    ModelPricing("claude-opus-4-7", "anthropic", 15.00, 75.00),
    ModelPricing("claude-sonnet-4-6", "anthropic", 3.00, 15.00),
    ModelPricing("claude-haiku-4-5", "anthropic", 0.25, 1.25),
    ModelPricing("claude-opus-4", "anthropic", 15.00, 75.00),
    ModelPricing("claude-sonnet-4", "anthropic", 3.00, 15.00),

    # ── DeepSeek ──
    ModelPricing("deepseek-chat", "deepseek", 0.27, 1.10),
    ModelPricing("deepseek-reasoner", "deepseek", 0.55, 2.19),

    # ── Google ──
    ModelPricing("gemini-2.5-pro", "google", 1.25, 5.00),
    ModelPricing("gemini-2.5-flash", "google", 0.15, 0.60),

    # ── Meta (via OpenRouter) ──
    ModelPricing("llama-4-maverick", "meta", 0.20, 0.80),
    ModelPricing("llama-4-scout", "meta", 0.10, 0.40),

    # ── Mistral ──
    ModelPricing("mistral-large", "mistral", 2.00, 6.00),
    ModelPricing("mistral-small", "mistral", 0.20, 0.60),

    # ── Qwen ──
    ModelPricing("qwen-max", "alibaba", 0.40, 1.20),
    ModelPricing("qwen-plus", "alibaba", 0.20, 0.60),
]


# ── Data classes ────────────────────────────────────────────────

@dataclass
class CostEntry:
    agent_name: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    session_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    warning: str | None = None

    def to_dict(self) -> dict:
        d = {
            "agent": self.agent_name,
            "model": self.model,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "tokens_total": self.tokens_in + self.tokens_out,
            "cost_usd": self.cost_usd,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
        }
        if self.warning:
            d["warning"] = self.warning
        return d


@dataclass
class BudgetConfig:
    limit_usd: float
    period: str = "monthly"  # "daily", "monthly", "total"
    current_usd: float = 0.0
    alert_threshold: float = 0.8   # alert at 80%
    auto_block: bool = True        # raise BudgetExceededError when exceeded

    @property
    def remaining(self) -> float:
        return round(self.limit_usd - self.current_usd, 6)

    @property
    def usage_pct(self) -> float:
        if self.limit_usd == 0:
            return 0.0
        return round(self.current_usd / self.limit_usd * 100, 2)

    @property
    def near_limit(self) -> bool:
        return self.usage_pct >= self.alert_threshold * 100


class BudgetExceededError(Exception):
    def __init__(self, limit: float, current: float, period: str):
        self.limit = limit
        self.current = current
        self.period = period
        super().__init__(
            f"Budget exceeded: ${current:.4f} / ${limit:.2f} ({period}). "
            f"Remaining calls blocked until reset."
        )


# ── Cost Tracker ────────────────────────────────────────────────

class CostTracker:
    def __init__(self):
        self._entries: list[CostEntry] = []
        self._budget: BudgetConfig | None = None
        self._pricing: dict[str, ModelPricing] = {
            p.model_id: p for p in DEFAULT_PRICING
        }
        self._db = None

    def set_database(self, db):
        self._db = db

    # ── Pricing ──────────────────────────────────────────────

    def get_pricing(self, model_id: str) -> ModelPricing | None:
        """Look up pricing for a model. Supports prefix matching."""
        if model_id in self._pricing:
            return self._pricing[model_id]
        for key, p in self._pricing.items():
            if model_id.startswith(key) or key.startswith(model_id):
                return p
        return None

    def register_pricing(
        self, model_id: str, input_price_per_1m: float,
        output_price_per_1m: float, provider: str = "custom",
    ) -> ModelPricing:
        p = ModelPricing(model_id, provider, input_price_per_1m, output_price_per_1m)
        self._pricing[model_id] = p
        return p

    def estimate(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """Estimate cost without recording an entry."""
        pricing = self.get_pricing(model)
        if pricing is None:
            raise KeyError(f"Unknown model '{model}'. Use register_pricing() to add it.")
        return pricing.calculate(tokens_in, tokens_out)

    # ── Tracking ─────────────────────────────────────────────

    def track(
        self, agent_name: str, model: str, tokens_in: int,
        tokens_out: int, session_id: str = "", workspace_id: str = "",
    ) -> CostEntry:
        pricing = self.get_pricing(model)
        warning = None
        if pricing is None:
            # Unknown model: use conservative default pricing
            pricing = ModelPricing(model, "unknown", 10.00, 30.00)
            warning = f"Unknown model '{model}', using default pricing ($10/$30 per 1M tokens)"
        cost = pricing.calculate(tokens_in, tokens_out)
        entry = CostEntry(
            agent_name=agent_name, model=model,
            tokens_in=tokens_in, tokens_out=tokens_out,
            cost_usd=cost, session_id=session_id,
            warning=warning,
        )
        self._entries.append(entry)

        if self._budget:
            self._budget.current_usd = round(self._budget.current_usd + cost, 6)
            if self._budget.auto_block and self._budget.current_usd > self._budget.limit_usd:
                raise BudgetExceededError(
                    self._budget.limit_usd, self._budget.current_usd,
                    self._budget.period,
                )

        if self._db and self._db.enabled:
            self._db.cost_insert(agent_name, model, tokens_in, tokens_out,
                                 cost, session_id, entry.timestamp, workspace_id)
        return entry

    # ── Queries ──────────────────────────────────────────────

    def get_agent_cost(self, agent_name: str) -> float:
        return round(sum(
            e.cost_usd for e in self._entries if e.agent_name == agent_name
        ), 6)

    def get_session_cost(self, session_id: str) -> float:
        return round(sum(
            e.cost_usd for e in self._entries if e.session_id == session_id
        ), 6)

    def get_model_cost(self, model: str) -> float:
        return round(sum(
            e.cost_usd for e in self._entries if e.model == model
        ), 6)

    def get_total_cost(self) -> float:
        return round(sum(e.cost_usd for e in self._entries), 6)

    def get_token_totals(self) -> dict:
        in_t = sum(e.tokens_in for e in self._entries)
        out_t = sum(e.tokens_out for e in self._entries)
        return {"tokens_in": in_t, "tokens_out": out_t, "tokens_total": in_t + out_t}

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    # ── Budget ───────────────────────────────────────────────

    def set_budget(
        self, limit_usd: float, period: str = "monthly",
        alert_threshold: float = 0.8, auto_block: bool = True,
        workspace_id: str = "",
    ) -> BudgetConfig:
        self._budget = BudgetConfig(
            limit_usd=limit_usd, period=period,
            alert_threshold=alert_threshold, auto_block=auto_block,
        )
        if self._db and self._db.enabled:
            self._db.budget_upsert(limit_usd, period, 0.0,
                                    alert_threshold, auto_block, workspace_id)
        return self._budget

    def check_budget(self) -> float:
        """Return remaining budget. Raises BudgetExceededError if over limit."""
        if self._budget is None:
            return float("inf")
        if self._budget.auto_block and self._budget.current_usd > self._budget.limit_usd:
            raise BudgetExceededError(
                self._budget.limit_usd, self._budget.current_usd,
                self._budget.period,
            )
        return self._budget.remaining

    def get_budget_status(self, workspace_id: str = "") -> dict | None:
        if self._budget is None:
            return None
        return {
            "limit_usd": self._budget.limit_usd,
            "current_usd": self._budget.current_usd,
            "remaining_usd": self._budget.remaining,
            "usage_pct": self._budget.usage_pct,
            "period": self._budget.period,
            "near_limit": self._budget.near_limit,
        }

    def reset_budget(self):
        self._budget = None

    # ── Report ───────────────────────────────────────────────

    def get_report(self, workspace_id: str = "") -> dict:
        """Comprehensive cost report by agent, session, and model."""
        by_agent: dict[str, float] = {}
        by_session: dict[str, float] = {}
        by_model: dict[str, float] = {}
        for e in self._entries:
            by_agent[e.agent_name] = round(by_agent.get(e.agent_name, 0) + e.cost_usd, 6)
            if e.session_id:
                by_session[e.session_id] = round(by_session.get(e.session_id, 0) + e.cost_usd, 6)
            by_model[e.model] = round(by_model.get(e.model, 0) + e.cost_usd, 6)

        tokens = self.get_token_totals()
        return {
            "total_cost_usd": self.get_total_cost(),
            "total_entries": len(self._entries),
            "tokens": tokens,
            "by_agent": by_agent,
            "by_session": by_session,
            "by_model": by_model,
            "budget": self.get_budget_status(),
        }

    # ── Export ───────────────────────────────────────────────

    def export_csv(self, filepath: str):
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "agent", "model", "tokens_in", "tokens_out",
                "tokens_total", "cost_usd", "session_id", "timestamp",
            ])
            writer.writeheader()
            for e in self._entries:
                writer.writerow(e.to_dict())

    def export_json(self, filepath: str):
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w") as f:
            json.dump([e.to_dict() for e in self._entries], f, indent=2, ensure_ascii=False)

    # ── Admin ────────────────────────────────────────────────

    def reset(self):
        self._entries.clear()
        self._budget = None


# ── Module-level convenience ────────────────────────────────────

_tracker: CostTracker | None = None


def get_tracker() -> CostTracker:
    global _tracker
    if _tracker is None:
        _tracker = CostTracker()
    return _tracker


def track_cost(
    agent_name: str, model: str, tokens_in: int,
    tokens_out: int, session_id: str = "",
) -> CostEntry:
    return get_tracker().track(agent_name, model, tokens_in, tokens_out, session_id)
