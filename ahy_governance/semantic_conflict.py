"""
Semantic conflict detection — LLM-powered, async, cached.

Architecture:
  1. Rule-based ConflictDetector returns immediately (fast path)
  2. Semantic detection runs async:
     a. Truncate text > 2000 chars
     b. Check embedding similarity (pre-filter, cheap)
     c. If similar enough → LLM pairwise judgment (expensive)
     d. Cache results to avoid duplicate calls
     e. Enforce daily rate limit
     f. Tag results with source="semantic" for auditability
"""

from __future__ import annotations

import hashlib
import time
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable


# ── Config ─────────────────────────────────────────────────────

MAX_TEXT_LENGTH = 2000        # chars, truncate beyond this
SIMILARITY_THRESHOLD = 0.75   # cosine similarity below this → skip LLM
DAILY_CALL_LIMIT = 500        # max LLM calls per day
CACHE_MAX_SIZE = 1000         # LRU cache entries
CACHE_TTL_SECONDS = 3600      # 1 hour


# ── Preprocessing ──────────────────────────────────────────────

def _truncate(text: str, max_len: int = MAX_TEXT_LENGTH) -> str:
    """Truncate long text, keeping start and end."""
    if len(text) <= max_len:
        return text
    half = max_len // 2
    return text[:half] + "\n... [truncated] ...\n" + text[-half:]


# ── Simple text embedding (character n-gram overlap, no external deps) ──

def _text_vector(text: str, n: int = 3) -> dict[str, int]:
    """Character n-gram frequency vector. Fast, no GPU needed."""
    text = text.lower()
    vec: dict[str, int] = {}
    for i in range(len(text) - n + 1):
        gram = text[i:i + n]
        vec[gram] = vec.get(gram, 0) + 1
    return vec


def _cosine_similarity(a: dict[str, int], b: dict[str, int]) -> float:
    """Cosine similarity between two sparse vectors."""
    if not a or not b:
        return 0.0
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    norm_a = sum(v ** 2 for v in a.values()) ** 0.5
    norm_b = sum(v ** 2 for v in b.values()) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Cache ─────────────────────────────────────────────────────

class _Cache:
    """Thread-safe LRU cache with TTL."""

    def __init__(self, max_size: int = CACHE_MAX_SIZE, ttl: int = CACHE_TTL_SECONDS):
        self._data: OrderedDict[str, tuple[float, object]] = OrderedDict()
        self._max = max_size
        self._ttl = ttl
        self._lock = threading.Lock()

    def _key(self, text_a: str, text_b: str) -> str:
        h = hashlib.sha256((text_a + "|||" + text_b).encode()).hexdigest()[:16]
        return h

    def get(self, text_a: str, text_b: str):
        k = self._key(text_a, text_b)
        with self._lock:
            if k not in self._data:
                return None
            ts, val = self._data[k]
            if time.time() - ts > self._ttl:
                del self._data[k]
                return None
            self._data.move_to_end(k)
            return val

    def set(self, text_a: str, text_b: str, value):
        k = self._key(text_a, text_b)
        with self._lock:
            if k in self._data:
                self._data.move_to_end(k)
            self._data[k] = (time.time(), value)
            while len(self._data) > self._max:
                self._data.popitem(last=False)


# ── Rate Limiter ────────────────────────────────────────────────

class _RateLimiter:
    """Daily call counter, reset at midnight UTC."""

    def __init__(self, daily_limit: int = DAILY_CALL_LIMIT):
        self._limit = daily_limit
        self._count = 0
        self._day = datetime.now(timezone.utc).day
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            today = datetime.now(timezone.utc).day
            if today != self._day:
                self._count = 0
                self._day = today
            if self._count >= self._limit:
                return False
            self._count += 1
            return True

    @property
    def remaining(self) -> int:
        return max(0, self._limit - self._count)


# ── Semantic Conflict Result ────────────────────────────────────

@dataclass
class SemanticResult:
    conflict_type: str            # "semantic_conflict" or "no_conflict"
    severity: str                 # "HIGH" | "MEDIUM" | "LOW"
    description: str
    agents_involved: list[str] = field(default_factory=list)
    suggestion: str = ""
    confidence: float = 0.0       # LLM confidence, 0-1
    source: str = "semantic"      # always "semantic" for auditability
    cached: bool = False          # was this from cache?


# ── LLM Prompt Template ─────────────────────────────────────────

PAIRWISE_PROMPT = """You are a conflict detector for multi-agent systems. Analyze whether two agent outputs semantically contradict each other.

Agent A output:
---
{text_a}
---

Agent B output:
---
{text_b}
---

Do these outputs have a semantic conflict? Consider:
- Factual contradictions (different numbers, dates, claims)
- Goal conflicts (optimizing for different objectives)
- Conflicting recommendations

Respond ONLY with JSON:
{{
  "has_conflict": true/false,
  "conflict_type": "fact_conflict" | "goal_conflict" | "recommendation_conflict" | "no_conflict",
  "severity": "HIGH" | "MEDIUM" | "LOW",
  "description": "One sentence describing the conflict if any",
  "suggestion": "One sentence suggesting how to resolve it"
}}"""


# ── Semantic Conflict Detector ──────────────────────────────────

class SemanticConflictDetector:
    """LLM-powered async semantic conflict detection.

    Usage:
        detector = SemanticConflictDetector(llm_callable=my_llm_function)
        # Async:
        results = await detector.detect_async(agent_outputs)
        # Or sync with callback:
        detector.detect(agent_outputs, on_result=my_callback)
    """

    def __init__(self, llm_callable: Callable | None = None,
                 max_text_len: int = MAX_TEXT_LENGTH,
                 similarity_threshold: float = SIMILARITY_THRESHOLD,
                 daily_limit: int = DAILY_CALL_LIMIT):
        self._llm = llm_callable
        self._max_text_len = max_text_len
        self._threshold = similarity_threshold
        self._cache = _Cache()
        self._limiter = _RateLimiter(daily_limit)

    def set_llm(self, llm_callable: Callable):
        self._llm = llm_callable

    def _preprocess(self, text: str) -> str:
        return _truncate(text.strip(), self._max_text_len)

    def _embedding_filter(self, text_a: str, text_b: str) -> bool:
        """Return True if texts are similar enough to warrant LLM check."""
        sim = _cosine_similarity(_text_vector(text_a), _text_vector(text_b))
        return sim >= self._threshold

    def check_pair(self, agent_a: str, output_a: str,
                    agent_b: str, output_b: str) -> SemanticResult | None:
        """Synchronous pair check. Returns None if filtered out or rate-limited."""
        # Preprocess
        text_a = self._preprocess(output_a)
        text_b = self._preprocess(output_b)

        # Check cache first
        cached = self._cache.get(text_a, text_b)
        if cached is not None:
            if isinstance(cached, SemanticResult):
                return cached
            return None  # cached as "no conflict"

        # Embedding pre-filter
        if not self._embedding_filter(text_a, text_b):
            self._cache.set(text_a, text_b, False)
            return None

        # Rate limit
        if not self._limiter.allow():
            return None

        # LLM judgment
        if self._llm is None:
            return None

        try:
            prompt = PAIRWISE_PROMPT.format(text_a=text_a, text_b=text_b)
            response = self._llm(prompt)
            result = self._parse_response(response, agent_a, agent_b)

            if result and result.conflict_type != "no_conflict":
                self._cache.set(text_a, text_b, result)
                return result
            else:
                self._cache.set(text_a, text_b, False)
                return None
        except Exception:
            return None

    def _parse_response(self, response: str, agent_a: str, agent_b: str) -> SemanticResult | None:
        """Parse LLM JSON response into SemanticResult."""
        import json as _json
        try:
            # Extract JSON from potential markdown code blocks
            text = response.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            data = _json.loads(text)

            if not data.get("has_conflict"):
                return SemanticResult(
                    conflict_type="no_conflict",
                    severity="LOW",
                    description="No semantic conflict detected",
                    agents_involved=[agent_a, agent_b],
                    source="semantic",
                )
            return SemanticResult(
                conflict_type=data.get("conflict_type", "semantic_conflict"),
                severity=data.get("severity", "MEDIUM"),
                description=data.get("description", ""),
                agents_involved=[agent_a, agent_b],
                suggestion=data.get("suggestion", ""),
                confidence=0.85,
                source="semantic",
            )
        except (_json.JSONDecodeError, KeyError, IndexError):
            return None

    def detect_batch(self, agent_outputs: dict[str, str],
                     existing_conflicts: list | None = None) -> list[SemanticResult]:
        """Check all agent pairs in a batch. Call after rule-based detection."""
        agents = list(agent_outputs.keys())
        results: list[SemanticResult] = []
        existing_pairs: set[tuple[str, str]] = set()

        if existing_conflicts:
            for c in existing_conflicts:
                agents_list = getattr(c, 'agents_involved', [])
                for i in range(len(agents_list)):
                    for j in range(i + 1, len(agents_list)):
                        existing_pairs.add((agents_list[i], agents_list[j]))

        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                a_name, b_name = agents[i], agents[j]
                # Skip pairs already caught by rule engine
                if (a_name, b_name) in existing_pairs or (b_name, a_name) in existing_pairs:
                    continue

                result = self.check_pair(
                    a_name, str(agent_outputs[a_name]),
                    b_name, str(agent_outputs[b_name]),
                )
                if result and result.conflict_type != "no_conflict":
                    results.append(result)

        return results

    def add_to_conflicts(self, semantic_results: list[SemanticResult],
                         conflicts: list) -> list:
        """Merge semantic results into existing conflict list."""
        from ahy_governance.conflict_detector import Conflict, ConflictType, Severity

        for sr in semantic_results:
            sev = {"HIGH": Severity.HIGH, "MEDIUM": Severity.MEDIUM, "LOW": Severity.LOW}.get(
                sr.severity, Severity.MEDIUM)
            c = Conflict(
                conflict_type=ConflictType.SEMANTIC_CONFLICT,
                severity=sev,
                agents_involved=sr.agents_involved,
                description=f"[semantic] {sr.description}",
                evidence={a: str(sr.confidence) for a in sr.agents_involved},
                suggestion=sr.suggestion,
                source="semantic",
            )
            conflicts.append(c)
        return conflicts

    @property
    def cache_stats(self) -> dict:
        return {
            "cache_size": len(self._cache._data),
            "daily_remaining": self._limiter.remaining,
            "daily_limit": self._limiter._limit,
        }
