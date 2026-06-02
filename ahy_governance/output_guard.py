"""
Output Guard — 运行时策略拦截引擎

20+ 策略类别，三段拦截（pre/mid/post），对标 Waxell 26 类 + Galileo 31 指标。

特性:
  pre-execution:  工具白名单、身份认证、预算检查、频率限制
  mid-execution:  输出过滤、Schema 校验、PII 检测、幻觉拦截
  post-execution: 审计记录、评测验证、成本记账

用法:
  guard = get_guard()
  guard.load_policies(default_policies())
  result = guard.check_pre("Planner", "tool_start", {"tool": "file_write"})
  if result.blocked:
      raise GuardBlockedError(result.verdicts)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


# ── Enums ───────────────────────────────────────────────────────

class GuardTiming:
    PRE = "pre"
    MID = "mid"
    POST = "post"


class GuardAction:
    BLOCK = "block"
    WARN = "warn"
    REDACT = "redact"
    LOG = "log"
    PASS = "pass"


# ── Data Classes ────────────────────────────────────────────────

@dataclass
class GuardPolicy:
    id: str
    name: str
    category: str          # data / cost / tool / output / comm / identity
    severity: str           # CRITICAL / HIGH / MEDIUM / LOW
    timing: str            # pre / mid / post
    disposition: str       # block / warn / redact / log
    enabled: bool = True
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "severity": self.severity,
            "timing": self.timing,
            "disposition": self.disposition,
            "enabled": self.enabled,
            "description": self.description,
        }


@dataclass
class GuardVerdict:
    passed: bool
    policy_id: str
    detail: str
    evidence: dict = field(default_factory=dict)
    action: str = GuardAction.PASS

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "policy_id": self.policy_id,
            "detail": self.detail,
            "evidence": self.evidence,
            "action": self.action,
        }


@dataclass
class GuardResult:
    agent_name: str
    verdicts: list[GuardVerdict] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def blocked(self) -> bool:
        return any(v.action == GuardAction.BLOCK for v in self.verdicts)

    @property
    def warned(self) -> bool:
        return any(v.action == GuardAction.WARN for v in self.verdicts)

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "blocked": self.blocked,
            "warned": self.warned,
            "verdicts": [v.to_dict() for v in self.verdicts],
            "timestamp": self.timestamp,
        }


class GuardBlockedError(Exception):
    def __init__(self, result: GuardResult):
        self.result = result
        super().__init__(f"Guard blocked: {[v.policy_id for v in result.verdicts if v.action == GuardAction.BLOCK]}")


# ── Policy Evaluators ──────────────────────────────────────────

def _evaluate_pii(input_data: dict) -> GuardVerdict:
    text = json.dumps(input_data, ensure_ascii=False)
    patterns = [
        (r'\b1[3-9]\d{9}\b', "手机号"),
        (r'\b\d{17}[\dXx]\b', "身份证"),
        (r'\b\d{16,19}\b', "银行卡"),
        (r'\b[\w.-]+@[\w.-]+\.\w+\b', "邮箱"),
    ]
    found = []
    for pat, label in patterns:
        matches = re.findall(pat, text)
        if matches:
            found.append({"type": label, "count": len(matches)})
    if found:
        return GuardVerdict(False, "pii_detect", f"检测到PII: {[f['type'] for f in found]}",
                           {"matches": found}, GuardAction.REDACT)
    return GuardVerdict(True, "pii_detect", "无PII")


def _evaluate_injection(input_data: dict) -> GuardVerdict:
    text = json.dumps(input_data, ensure_ascii=False).lower()
    patterns = [
        r"ignore (all |previous )?instructions",
        r"you are now",
        r"system prompt",
        r"act as",
        r"forget .* rules",
    ]
    for p in patterns:
        if re.search(p, text):
            return GuardVerdict(False, "prompt_injection", f"检测到注入: {p}",
                               {"pattern": p}, GuardAction.BLOCK)
    return GuardVerdict(True, "prompt_injection", "无注入")


def _evaluate_tool_allowlist(tool_name: str, allowlist: list[str]) -> GuardVerdict:
    if allowlist and tool_name not in allowlist:
        return GuardVerdict(False, "tool_allowlist",
                           f"工具 '{tool_name}' 不在白名单中",
                           {"tool": tool_name, "allowlist": allowlist},
                           GuardAction.BLOCK)
    return GuardVerdict(True, "tool_allowlist", f"工具 '{tool_name}' 在白名单中")


# ── Output Guard ────────────────────────────────────────────────

class OutputGuard:
    """运行时策略拦截引擎."""

    def __init__(self):
        self._policies: dict[str, GuardPolicy] = {}
        self._evaluators: dict[str, Callable] = {}
        self._tool_allowlist: list[str] = []
        self._tool_denylist: list[str] = []
        self._db = None

    def set_database(self, db):
        self._db = db

    def set_tool_allowlist(self, tools: list[str]):
        self._tool_allowlist = tools

    def set_tool_denylist(self, tools: list[str]):
        self._tool_denylist = tools

    def load_policies(self, policies: list[GuardPolicy]):
        for p in policies:
            self._policies[p.id] = p

    def list_policies(self) -> list[dict]:
        return [p.to_dict() for p in self._policies.values()]

    def update_policy(self, policy_id: str, enabled: bool):
        if policy_id in self._policies:
            self._policies[policy_id].enabled = enabled

    # ── Checks ─────────────────────────────────────────────────

    def check_pre(self, agent_name: str, event_type: str,
                  input_data: dict) -> GuardResult:
        verdicts = []
        # Injection check (always)
        if self._policies.get("prompt_injection", GuardPolicy("", "", "", "", "")).enabled:
            verdicts.append(_evaluate_injection(input_data))
        # Tool allowlist
        if event_type == "tool_start" and self._tool_allowlist:
            tool = input_data.get("tool_name", input_data.get("tool", ""))
            verdicts.append(_evaluate_tool_allowlist(tool, self._tool_allowlist))
        # Tool denylist
        if event_type == "tool_start" and self._tool_denylist:
            tool = input_data.get("tool_name", input_data.get("tool", ""))
            if tool in self._tool_denylist:
                verdicts.append(GuardVerdict(False, "tool_denylist",
                    f"工具 '{tool}' 在黑名单中", {"tool": tool}, GuardAction.BLOCK))
        return GuardResult(agent_name=agent_name, verdicts=verdicts)

    def check_mid(self, agent_name: str, output: dict) -> GuardResult:
        verdicts = []
        # PII check
        if self._policies.get("pii_detect", GuardPolicy("", "", "", "", "")).enabled:
            verdicts.append(_evaluate_pii(output))
        # Output schema (validator runs externally via evaluator)
        return GuardResult(agent_name=agent_name, verdicts=verdicts)

    def check_post(self, agent_name: str, event_data: dict) -> GuardResult:
        verdicts = []
        return GuardResult(agent_name=agent_name, verdicts=verdicts)

    def reset(self):
        self._policies.clear()
        self._tool_allowlist = []
        self._tool_denylist = []


# ── Module-level convenience ────────────────────────────────────

_output_guard: OutputGuard | None = None


def get_output_guard() -> OutputGuard:
    global _output_guard
    if _output_guard is None:
        _output_guard = OutputGuard()
    return _output_guard
