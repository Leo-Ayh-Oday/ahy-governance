"""
Quality Gate — CI/CD 质量门禁

对标 Braintrust GitHub Action: PR 跑 eval，低于阈值 block merge。

用法:
  gate = QualityGate(
      dataset_id="ds-xxx",
      scorers=["hallucination_check", "output_schema"],
      thresholds={"hallucination_check": 0.8, "overall": 0.7},
  )
  result = gate.run()
  if not result.passed:
      print(result.to_github_comment())
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class GateConfig:
    gate_id: str
    name: str = ""
    dataset_id: str = ""
    scorers: list[str] = field(default_factory=list)
    thresholds: dict[str, float] = field(default_factory=dict)
    on_failure: str = "block"

    def to_dict(self) -> dict:
        return {
            "gate_id": self.gate_id, "name": self.name,
            "dataset_id": self.dataset_id, "scorers": self.scorers,
            "thresholds": self.thresholds, "on_failure": self.on_failure,
        }


@dataclass
class GateResult:
    gate_id: str
    passed: bool
    overall_score: float
    per_scorer: dict[str, dict] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    detail: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "gate_id": self.gate_id, "passed": self.passed,
            "overall_score": self.overall_score,
            "per_scorer": self.per_scorer, "failures": self.failures,
            "detail": self.detail, "created_at": self.created_at,
        }

    def to_github_comment(self) -> str:
        """生成 GitHub PR 评论用的 Markdown."""
        icon = "✅" if self.passed else "❌"
        lines = [
            f"## {icon} Ahy Quality Gate: {self.gate_id}",
            f"",
            f"**Overall Score**: {self.overall_score:.1%}",
            f"**Status**: {'PASSED' if self.passed else 'FAILED'}",
            f"",
            f"| Scorer | Score | Threshold | Status |",
            f"|--------|-------|-----------|--------|",
        ]
        for name, info in self.per_scorer.items():
            score = info.get("value", 0)
            threshold = info.get("threshold", 0)
            ok = "✅" if score >= threshold else "❌"
            lines.append(f"| {name} | {score:.1%} | {threshold:.1%} | {ok} |")
        if self.failures:
            lines.append(f"")
            lines.append(f"### Failures")
            for f in self.failures:
                lines.append(f"- {f}")
        return "\n".join(lines)


class QualityGate:
    """CI/CD 质量门禁执行器."""

    def __init__(self, gate_id: str, config: GateConfig | None = None):
        self.gate_id = gate_id
        self.config = config or GateConfig(gate_id=gate_id)
        self._db = None

    def set_database(self, db):
        self._db = db

    def run(self, workspace_id: str = "") -> GateResult:
        """执行质量门禁."""
        from .evaluator import get_eval_registry

        registry = get_eval_registry()
        if self._db and registry._db is None:
            registry.set_database(self._db)

        eval_run = registry.run_eval(
            self.config.dataset_id,
            self.config.scorers,
            workspace_id,
        )
        summary = eval_run.summary

        per_scorer = {}
        failures = []
        overall = self.config.thresholds.get("overall", 0.7)
        passed = summary.avg_score >= overall

        for name, score in summary.per_scorer.items():
            threshold = self.config.thresholds.get(name, 0.7)
            ok = score >= threshold
            per_scorer[name] = {"value": score, "threshold": threshold, "passed": ok}
            if not ok:
                failures.append(f"{name}: {score:.1%} < {threshold:.1%}")

        if not passed:
            failures.insert(0, f"overall: {summary.avg_score:.1%} < {overall:.1%}")

        detail = f"{summary.passed}/{summary.total} cases passed, avg {summary.avg_score:.1%}"

        return GateResult(
            gate_id=self.gate_id, passed=passed and len(failures) <= (1 if not passed else 0),
            overall_score=summary.avg_score,
            per_scorer=per_scorer, failures=failures, detail=detail,
        )


# ── Module-level convenience ────────────────────────────────────


def run_quality_gate(
    gate_id: str, dataset_id: str, scorers: list[str],
    thresholds: dict[str, float] | None = None,
    workspace_id: str = "",
) -> GateResult:
    config = GateConfig(
        gate_id=gate_id, dataset_id=dataset_id,
        scorers=scorers, thresholds=thresholds or {},
    )
    gate = QualityGate(gate_id, config)
    return gate.run(workspace_id)
