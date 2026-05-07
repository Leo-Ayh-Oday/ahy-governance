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
from .interfaces import CostTracker as CostTrackerABC
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .storage import Database


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

    def to_dict(self) -> dict:
        return {
            "agent": self.agent_name,
            "model": self.model,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "tokens_total": self.tokens_in + self.tokens_out,
            "cost_usd": self.cost_usd,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
        }


@dataclass
class BudgetConfig:
    limit_usd: float
    period: str = "monthly"  # "daily", "monthly", "total"
    current_usd: float = 0.0
    alert_threshold: float = 0.8   # alert at 80%
    auto_block: bool = True        # raise BudgetExceededError when exceeded
    anomaly_threshold_usd: float = 2.0     # single-call cost > this = anomaly
    anomaly_threshold_tokens: int = 100_000  # single-call tokens > this = anomaly
    anomaly_count: int = 0          # running count of anomalies detected

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


@dataclass
class AnomalyEvent:
    agent_name: str
    model: str
    cost_usd: float
    tokens_total: int
    reason: str  # e.g. "cost_spike", "token_spike"
    session_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── Cost Tracker ────────────────────────────────────────────────

class CostTracker(CostTrackerABC):
    def __init__(self, db: Database | None = None):
        self._db = db
        self._entries: list[CostEntry] = []
        self._anomalies: list[AnomalyEvent] = []
        self._budget: BudgetConfig | None = None
        self._pricing: dict[str, ModelPricing] = {
            p.model_id: p for p in DEFAULT_PRICING
        }
        # Load pricing from DB if available
        if self._use_db:
            for row in self._db.pricing_all():
                if row["model_id"] not in self._pricing:
                    self._pricing[row["model_id"]] = ModelPricing(
                        model_id=row["model_id"], provider=row["provider"],
                        input_price_per_1m=row["input_price_per_1m"],
                        output_price_per_1m=row["output_price_per_1m"],
                        note=row["note"] or "",
                    )
            # Load budget from DB
            b = self._db.budget_get()
            if b:
                self._budget = BudgetConfig(
                    limit_usd=b["limit_usd"], period=b["period"],
                    current_usd=b["current_usd"], alert_threshold=b["alert_threshold"],
                    auto_block=bool(b["auto_block"]),
                )

    @property
    def _use_db(self) -> bool:
        return self._db is not None and self._db.enabled

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
        if self._use_db:
            self._db.pricing_upsert(model_id, provider, input_price_per_1m, output_price_per_1m, "")
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
        if pricing is None:
            raise KeyError(
                f"Unknown model '{model}'. Use register_pricing() to add custom pricing."
            )
        cost = pricing.calculate(tokens_in, tokens_out)
        entry = CostEntry(
            agent_name=agent_name, model=model,
            tokens_in=tokens_in, tokens_out=tokens_out,
            cost_usd=cost, session_id=session_id,
        )
        self._entries.append(entry)

        # Anomaly detection — per-call check
        if self._budget:
            tokens_total = tokens_in + tokens_out
            if cost > self._budget.anomaly_threshold_usd or tokens_total > self._budget.anomaly_threshold_tokens:
                reason = "cost_spike" if cost > self._budget.anomaly_threshold_usd else "token_spike"
                self._anomalies.append(AnomalyEvent(
                    agent_name=agent_name, model=model,
                    cost_usd=cost, tokens_total=tokens_total,
                    reason=reason, session_id=session_id,
                ))
                self._budget.anomaly_count += 1

        # Persist to DB
        if self._use_db:
            self._db.cost_insert(agent_name, model, tokens_in, tokens_out, cost, session_id, entry.timestamp, workspace_id)
            if self._budget:
                self._db.budget_update_current(cost, workspace_id)

        if self._budget:
            self._budget.current_usd = round(self._budget.current_usd + cost, 6)
            if self._budget.auto_block and self._budget.current_usd > self._budget.limit_usd:
                raise BudgetExceededError(
                    self._budget.limit_usd, self._budget.current_usd,
                    self._budget.period,
                )

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

    @property
    def anomaly_count(self) -> int:
        return self._budget.anomaly_count if self._budget else 0

    def get_anomalies(self, limit: int = 20) -> list[dict]:
        return [{
            "agent_name": a.agent_name,
            "model": a.model,
            "cost_usd": a.cost_usd,
            "tokens_total": a.tokens_total,
            "reason": a.reason,
            "session_id": a.session_id,
            "timestamp": a.timestamp,
        } for a in self._anomalies[-limit:]]

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
        if self._use_db:
            self._db.budget_upsert(limit_usd, period, 0.0, alert_threshold, auto_block, workspace_id)
        return self._budget

    def get_budget_status(self, workspace_id: str = "") -> dict | None:
        if self._use_db:
            b = self._db.budget_get(workspace_id)
            if b:
                return {
                    "limit_usd": b["limit_usd"],
                    "current_usd": b["current_usd"],
                    "total_cost": b["current_usd"],
                    "remaining_usd": round(b["limit_usd"] - b["current_usd"], 6),
                    "usage_pct": round(b["current_usd"] / b["limit_usd"] * 100, 2) if b["limit_usd"] else 0,
                    "period": b["period"],
                    "alert_threshold": b.get("alert_threshold", 0.8),
                    "auto_block": bool(b.get("auto_block", False)),
                    "near_limit": b["current_usd"] / b["limit_usd"] >= b["alert_threshold"] if b["limit_usd"] else False,
                    "anomaly_count": self.anomaly_count,
                    "anomaly_threshold_usd": self._budget.anomaly_threshold_usd if self._budget else 2.0,
                }
        if self._budget is None:
            return None
        return {
            "limit_usd": self._budget.limit_usd,
            "current_usd": self._budget.current_usd,
            "total_cost": self._budget.current_usd,
            "remaining_usd": self._budget.remaining,
            "usage_pct": self._budget.usage_pct,
            "period": self._budget.period,
            "alert_threshold": self._budget.alert_threshold,
            "auto_block": self._budget.auto_block,
            "near_limit": self._budget.near_limit,
            "anomaly_count": self._budget.anomaly_count,
            "anomaly_threshold_usd": self._budget.anomaly_threshold_usd,
        }

    # ── ABC interface methods ─────────────────────────────────

    def name(self) -> str:
        return "default"

    def estimate_from_request(self, request: dict) -> float:
        """ABC-compatible: estimate cost from a dict with model/tokens_in/tokens_out."""
        return self.estimate(
            model=request.get("model", "unknown"),
            tokens_in=request.get("tokens_in", 0),
            tokens_out=request.get("tokens_out", 0),
        )

    def should_throttle(self, agent_id: str, budget_limit: float) -> bool:
        """Return True if the agent exceeds or is near budget limit."""
        if self._budget is None:
            return False
        cost = self.get_agent_cost(agent_id)
        return cost >= budget_limit * self._budget.alert_threshold

    # ── Budget check ─────────────────────────────────────────

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

    def reset_budget(self):
        self._budget = None

    # ── Report ───────────────────────────────────────────────

    def get_report(self, workspace_id: str = "") -> dict:
        """Comprehensive cost report by agent, session, and model."""
        if self._use_db:
            entries = self._db.cost_all(workspace_id)
            by_agent: dict[str, float] = {}
            by_session: dict[str, float] = {}
            by_model: dict[str, float] = {}
            for e in entries:
                by_agent[e["agent_name"]] = round(by_agent.get(e["agent_name"], 0) + e["cost_usd"], 6)
                if e["session_id"]:
                    by_session[e["session_id"]] = round(by_session.get(e["session_id"], 0) + e["cost_usd"], 6)
                by_model[e["model"]] = round(by_model.get(e["model"], 0) + e["cost_usd"], 6)
            tokens = self._db.cost_token_totals(workspace_id)
            return {
                "total_cost_usd": self._db.cost_total_usd(workspace_id),
                "total_entries": self._db.cost_count(workspace_id),
                "tokens": tokens,
                "by_agent": by_agent,
                "by_session": by_session,
                "by_model": by_model,
                "budget": self.get_budget_status(workspace_id),
            }

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
        if self._use_db:
            self._db.clear_all()


# ── Module-level convenience ────────────────────────────────────

_tracker: CostTracker | None = None
_db: Database | None = None


def set_database(db: Database | None):
    global _db, _tracker
    _db = db
    _tracker = None


def get_tracker() -> CostTracker:
    global _tracker, _db
    if _tracker is None:
        if _db is None:
            db_path = os.environ.get("AHY_DB_PATH", "")
            if db_path:
                from .storage import Database
                _db = Database(db_path)
        _tracker = CostTracker(db=_db)
    return _tracker


def track_cost(
    agent_name: str, model: str, tokens_in: int,
    tokens_out: int, session_id: str = "",
) -> CostEntry:
    return get_tracker().track(agent_name, model, tokens_in, tokens_out, session_id)
