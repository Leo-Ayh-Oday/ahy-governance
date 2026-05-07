"""
Prompt Guard — 提示词注入检测 + 敏感数据脱敏

特性:
  12+ 内置注入模式（中英文）
  PII 脱敏: 手机号/身份证/银行卡/邮箱
  自定义模式注册
  联合净化管道 (detect + mask → SanitizeResult)

用法:
  guard = PromptGuard()
  result = guard.sanitize(user_input)
  if not result.is_clean:
      print(f"Blocked: injection confidence={result.injection_confidence}")
  safe_text = result.clean_text
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable


# ── Default injection patterns ──────────────────────────────────

@dataclass
class InjectionPattern:
    name: str
    pattern: str  # regex
    severity: str  # "critical", "high", "medium", "low"
    flags: int = re.IGNORECASE


DEFAULT_INJECTION_PATTERNS: list[InjectionPattern] = [
    # ── Direct override (critical) ──
    InjectionPattern("ignore_instructions", r"ignore\s+(all\s+)?(previous|prior|above|the\s+)?\s*(instructions?|messages?|conversation|context|everything|context)", "critical"),
    InjectionPattern("system_override", r"(override|bypass|disable)\s+(all\s+)?(safety\s+)?(guidelines?|restrictions?|rules?|protections?|filters?)", "critical"),
    InjectionPattern("you_are_role", r"you\s+are\s+(now\s+)?(DAN|an?\s+unrestricted|no\s+longer|an?\s+evil|a?\s+different\s+(AI|model|assistant))", "critical"),
    InjectionPattern("forget_programming", r"(forget|erase|delete|clear)\s+(your\s+)?(training|programming|instructions?|system\s+prompt|knowledge)", "critical"),

    # ── Prompt extraction (high) ──
    InjectionPattern("reveal_prompt", r"(tell|show|reveal|output|print|display|leak)\s+(me\s+)?(the\s+)?(your\s+)?(system\s+)?(prompt|instructions?|message|hidden|internal|secret)", "high"),
    InjectionPattern("template_injection", r"\{\{.*?\}\}", "high"),

    # ── Role hijack (high) ──
    InjectionPattern("role_hijack", r"(from\s+now\s+on|starting\s+now|beginning\s+now)\s*,?\s*(you\s+(will|must|are|should))", "high"),
    InjectionPattern("new_directive", r"(your\s+new\s+(task|role|job|directive|instruction|objective)\s+is)", "high"),

    # ── Jailbreak (high) ──
    InjectionPattern("jailbreak", r"(do\s+anything\s+now|no\s+restrictions?|unlimited\s+mode|developer\s+mode|god\s+mode)", "high"),

    # ── Chinese injection patterns ──
    InjectionPattern("cn_ignore_instructions", r"(忽略|无视|忘记|清除)\s*(所有|之前|前面|上述|以上|的|\s)*(指令|指示|对话|消息|规则|设定|编程)", "critical"),
    InjectionPattern("cn_system_prompt", r"(告诉|输出|打印|显示|泄露|透露)\s*(我|给我)?\s*(你的?|[你您]的?)\s*(系统\s*)?(提示词|提示|指令|设定|秘密|隐藏)", "high"),
    InjectionPattern("cn_role_hijack", r"(从现在起|从现在开始|接下来)\s*,?\s*(你是|你要|你必须|你扮演)", "high"),

    # ── Hybrid / mixed-cn-en patterns ──
    InjectionPattern("hybrid_ignore", r"(?:ignore|忽略)\s+.*?(?:instructions?|指令|规则|限制)", "high"),

    # ── Code/script injection (medium) ──
    InjectionPattern("code_injection", r"(<script|<iframe|javascript\s*:|eval\s*\(|exec\s*\()", "medium"),
]


# ── Default PII patterns ────────────────────────────────────────

@dataclass
class PIIPattern:
    name: str
    pattern: str  # regex with named groups or positional
    mask_fn: Callable[[re.Match], str]


def _mask_phone(m: re.Match) -> str:
    num = m.group(0)
    return num[:3] + "****" + num[-4:]


def _mask_id_card(m: re.Match) -> str:
    num = m.group(0)
    return num[:6] + "****" + num[-4:]


def _mask_bank_card(m: re.Match) -> str:
    num = m.group(0)
    return "****" + num[-4:]


def _mask_email(m: re.Match) -> str:
    full = m.group(0)
    local, domain = full.split("@", 1)
    return local[0] + "***@" + domain


DEFAULT_PII_PATTERNS: list[PIIPattern] = [
    # ID card FIRST — its digits can contain false phone matches
    PIIPattern("id_card", r"\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]", _mask_id_card),
    # Phone second — mask after ID cards are already redacted
    PIIPattern("phone", r"1[3-9]\d{9}", _mask_phone),
    # Bank card: 16-19 digits
    PIIPattern("bank_card", r"\b\d{16,19}\b", _mask_bank_card),
    # Email
    PIIPattern("email", r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", _mask_email),
]


# ── Result types ────────────────────────────────────────────────

@dataclass
class InjectionResult:
    detected: bool
    confidence: float          # 0.0 ~ 1.0
    matched_patterns: list[str]
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "detected": self.detected,
            "confidence": self.confidence,
            "matched_patterns": self.matched_patterns,
            "evidence": self.evidence,
        }


@dataclass
class MaskResult:
    original: str
    masked: str
    redactions: list[dict]     # [{type, original, masked}]

    def to_dict(self) -> dict:
        return {
            "original": self.original,
            "masked": self.masked,
            "redaction_count": len(self.redactions),
            "redactions": self.redactions,
        }


@dataclass
class SanitizeResult:
    original_text: str
    clean_text: str
    is_clean: bool
    injection_detected: bool
    injection_confidence: float
    injection_matches: list[str]
    redaction_count: int

    def to_dict(self) -> dict:
        return {
            "is_clean": self.is_clean,
            "injection_detected": self.injection_detected,
            "injection_confidence": self.injection_confidence,
            "injection_matches": self.injection_matches,
            "redaction_count": self.redaction_count,
            "clean_text": self.clean_text,
        }


# ── PromptGuard ─────────────────────────────────────────────────

class PromptGuard:
    def __init__(self):
        self._injection_patterns: dict[str, InjectionPattern] = {
            p.name: p for p in DEFAULT_INJECTION_PATTERNS
        }
        self._pii_patterns: dict[str, PIIPattern] = {
            p.name: p for p in DEFAULT_PII_PATTERNS
        }

    # ── Injection Detection ───────────────────────────────────

    def detect_injection(self, text: str) -> InjectionResult:
        if not text or not text.strip():
            return InjectionResult(
                detected=False, confidence=0.0,
                matched_patterns=[], evidence=[],
            )

        matched: list[str] = []
        evidence: list[str] = []
        severity_scores = {"critical": 1.0, "high": 0.7, "medium": 0.4, "low": 0.2}

        for ip in self._injection_patterns.values():
            m = re.search(ip.pattern, text, ip.flags)
            if m:
                matched.append(ip.name)
                # Extract context around the match
                start = max(0, m.start() - 20)
                end = min(len(text), m.end() + 20)
                evidence.append(text[start:end])

        if not matched:
            return InjectionResult(
                detected=False, confidence=0.0,
                matched_patterns=[], evidence=[],
            )

        # Confidence: weighted by severity, capped at 1.0
        max_severity = max(
            severity_scores.get(self._injection_patterns[n].severity, 0.2)
            for n in matched
        )
        # Bonus for multiple matches
        multi_bonus = min(0.3, len(matched) * 0.1)
        confidence = min(1.0, max_severity + multi_bonus)

        return InjectionResult(
            detected=True, confidence=round(confidence, 2),
            matched_patterns=matched, evidence=evidence,
        )

    # ── PII Masking ───────────────────────────────────────────

    def mask_pii(self, text: str) -> MaskResult:
        masked = text
        redactions: list[dict] = []

        for pp in self._pii_patterns.values():
            matches = list(re.finditer(pp.pattern, masked))
            for m in reversed(matches):  # replace from end to preserve positions
                original = m.group(0)
                replacement = pp.mask_fn(m)
                masked = masked[:m.start()] + replacement + masked[m.end():]
                redactions.append({
                    "type": pp.name,
                    "original": original,
                    "masked": replacement,
                })

        # Sort redactions by original appearance order
        redactions.sort(key=lambda r: text.find(r["original"]) if r["original"] in text else 9999)

        return MaskResult(original=text, masked=masked, redactions=redactions)

    # ── Sanitize Pipeline ─────────────────────────────────────

    def sanitize(self, text: str) -> SanitizeResult:
        injection = self.detect_injection(text)
        mask = self.mask_pii(text)

        return SanitizeResult(
            original_text=text,
            clean_text=mask.masked,
            is_clean=not injection.detected,
            injection_detected=injection.detected,
            injection_confidence=injection.confidence,
            injection_matches=injection.matched_patterns,
            redaction_count=len(mask.redactions),
        )

    # ── Custom Patterns ───────────────────────────────────────

    def add_injection_pattern(self, name: str, pattern: str, severity: str = "medium"):
        self._injection_patterns[name] = InjectionPattern(
            name=name, pattern=pattern, severity=severity,
        )

    def add_pii_pattern(self, name: str, pattern: str, mask_fn: Callable[[re.Match], str]):
        self._pii_patterns[name] = PIIPattern(name=name, pattern=pattern, mask_fn=mask_fn)

    def remove_pattern(self, name: str) -> bool:
        if name in self._injection_patterns:
            del self._injection_patterns[name]
            return True
        if name in self._pii_patterns:
            del self._pii_patterns[name]
            return True
        return False

    # ── Admin ─────────────────────────────────────────────────

    def reset(self):
        self._injection_patterns = {
            p.name: p for p in DEFAULT_INJECTION_PATTERNS
        }
        self._pii_patterns = {
            p.name: p for p in DEFAULT_PII_PATTERNS
        }


# ── Module-level convenience ────────────────────────────────────

_guard: PromptGuard | None = None


def get_guard() -> PromptGuard:
    global _guard
    if _guard is None:
        _guard = PromptGuard()
    return _guard


def sanitize_prompt(text: str) -> SanitizeResult:
    return get_guard().sanitize(text)
