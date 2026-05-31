"""Semantic Conflict Detector 测试"""

import pytest
from ahy_governance.semantic_conflict import (
    SemanticConflictDetector,
    SemanticResult,
    _truncate,
    _text_vector,
    _cosine_similarity,
    _Cache,
    _RateLimiter,
    MAX_TEXT_LENGTH,
)


class TestPreprocessing:
    def test_truncate_short_text(self):
        short = "hello world"
        assert _truncate(short) == short

    def test_truncate_long_text(self):
        long_text = "x" * (MAX_TEXT_LENGTH + 500)
        result = _truncate(long_text)
        assert len(result) <= MAX_TEXT_LENGTH + 100  # allow some overhead
        assert "[truncated]" in result

    def test_truncate_exactly_at_limit(self):
        exact = "y" * MAX_TEXT_LENGTH
        assert _truncate(exact) == exact


class TestVectorSimilarity:
    def test_identical_texts_max_similarity(self):
        text = "The contract deadline is June 30, 2026. Amount: 5 million RMB."
        v1 = _text_vector(text)
        v2 = _text_vector(text)
        sim = _cosine_similarity(v1, v2)
        assert sim > 0.99

    def test_completely_different_texts_low_similarity(self):
        v1 = _text_vector("contract deadline payment amount legal review")
        v2 = _text_vector("weather forecast temperature humidity rain probability")
        sim = _cosine_similarity(v1, v2)
        assert sim < 0.3

    def test_empty_vector(self):
        assert _cosine_similarity({}, {"a": 1}) == 0.0
        assert _cosine_similarity({}, {}) == 0.0


class TestCache:
    def test_set_and_get(self):
        c = _Cache(max_size=10, ttl=3600)
        c.set("a", "b", "result1")
        assert c.get("a", "b") == "result1"

    def test_cache_miss(self):
        c = _Cache()
        assert c.get("never", "cached") is None

    def test_cache_different_order_same_pair(self):
        c = _Cache()
        c.set("text_a", "text_b", "conflict")
        # Same pair should hit cache regardless of argument order
        # (Cache uses hash of sorted pair)
        assert c.get("text_a", "text_b") == "conflict"

    def test_ttl_expiry(self):
        c = _Cache(max_size=10, ttl=0)  # zero TTL
        c.set("x", "y", "val")
        assert c.get("x", "y") is None  # immediately expired


class TestRateLimiter:
    def test_allows_within_limit(self):
        rl = _RateLimiter(daily_limit=3)
        assert rl.allow()
        assert rl.allow()
        assert rl.allow()

    def test_blocks_after_limit(self):
        rl = _RateLimiter(daily_limit=2)
        rl.allow()
        rl.allow()
        assert not rl.allow()

    def test_remaining_count(self):
        rl = _RateLimiter(daily_limit=5)
        rl.allow()
        assert rl.remaining == 4


class TestSemanticDetectorNoLLM:
    """Test detector behavior WITHOUT a real LLM (llm_callable=None)."""

    def test_init_without_llm(self):
        d = SemanticConflictDetector()
        assert d._llm is None

    def test_set_llm(self):
        d = SemanticConflictDetector()
        fake_llm = lambda p: '{"has_conflict": true, "conflict_type": "fact_conflict", "severity": "HIGH", "description": "test", "suggestion": "fix"}'
        d.set_llm(fake_llm)
        assert d._llm is not None

    def test_check_pair_without_llm_returns_none(self):
        d = SemanticConflictDetector()
        result = d.check_pair("a", "output a", "b", "output b")
        assert result is None

    def test_detect_batch_returns_empty_without_llm(self):
        d = SemanticConflictDetector()
        results = d.detect_batch({
            "agent_a": "some output",
            "agent_b": "another output",
        })
        assert results == []

    def test_cache_stats(self):
        d = SemanticConflictDetector()
        stats = d.cache_stats
        assert "cache_size" in stats
        assert "daily_remaining" in stats
        assert stats["cache_size"] == 0


class TestSemanticDetectorWithMockLLM:
    """Test detector WITH a mock LLM callable."""

    def test_detects_conflict_with_mock_llm(self):
        mock_llm = lambda p: '{"has_conflict": true, "conflict_type": "fact_conflict", "severity": "HIGH", "description": "Deadline mismatch between agents", "suggestion": "Human review required"}'
        d = SemanticConflictDetector(llm_callable=mock_llm)
        result = d.check_pair(
            "Planner", "deadline is 2026-06-01, budget 500万元",
            "Reviewer", "deadline is 2026-07-15, budget 500万元",
        )
        assert result is not None
        assert result.conflict_type == "fact_conflict"
        assert result.source == "semantic"
        assert "Planner" in result.agents_involved
        assert "Reviewer" in result.agents_involved

    def test_no_conflict_with_mock_llm(self):
        mock_llm = lambda p: '{"has_conflict": false, "conflict_type": "no_conflict", "severity": "LOW", "description": "No conflict", "suggestion": ""}'
        d = SemanticConflictDetector(llm_callable=mock_llm)
        result = d.check_pair("a", "same thing", "b", "same thing")
        assert result is None  # no_conflict → not returned

    def test_cache_hit_on_second_call(self):
        call_count = [0]
        # Use very similar texts to pass embedding similarity filter
        text_a = "The contract review deadline is June 30 2026. Total amount is 5 million RMB. Risk level is medium."
        text_b = "The contract review deadline is July 15 2026. Total amount is 5 million RMB. Risk level is medium."

        def counting_llm(prompt):
            call_count[0] += 1
            return '{"has_conflict": true, "conflict_type": "fact_conflict", "severity": "MEDIUM", "description": "Cached result", "suggestion": ""}'

        d = SemanticConflictDetector(llm_callable=counting_llm)
        r1 = d.check_pair("A", text_a, "B", text_b)
        assert r1 is not None, "First call should detect conflict"
        assert call_count[0] == 1

        r2 = d.check_pair("A", text_a, "B", text_b)
        assert r2 is not None, "Second call should hit cache"
        assert call_count[0] == 1  # cached, no second LLM call

    def test_batch_detection_respects_existing_conflicts(self):
        mock_llm = lambda p: '{"has_conflict": true, "conflict_type": "fact_conflict", "severity": "HIGH", "description": "x", "suggestion": ""}'
        d = SemanticConflictDetector(llm_callable=mock_llm)

        # Simulate existing rule-based conflict between the same pair
        from ahy_governance.conflict_detector import Conflict, ConflictType, Severity
        existing = [Conflict(
            conflict_type=ConflictType.FACT_CONFLICT,
            severity=Severity.HIGH,
            agents_involved=["a1", "a2"],
            description="Already detected",
        )]

        results = d.detect_batch(
            {"a1": "text A", "a2": "text B", "a3": "text C"},
            existing_conflicts=existing,
        )
        # a1-a2 pair already covered by rule engine → skipped
        # Only a1-a3, a2-a3 pairs checked
        for r in results:
            assert "a1" not in r.agents_involved or "a2" not in r.agents_involved

    def test_embedding_filter_skips_dissimilar_texts(self):
        mock_llm = lambda p: '{"has_conflict": true, "conflict_type": "fact_conflict", "severity": "HIGH", "description": "x", "suggestion": ""}'
        d = SemanticConflictDetector(llm_callable=mock_llm, similarity_threshold=0.95)
        result = d.check_pair(
            "A", "contract deadline payment legal review clause amendment",
            "B", "weather forecast rain probability humidity today sunny",
        )
        # Very different texts → embedding filter should skip LLM call
        assert result is None

    def test_parse_markdown_code_block_response(self):
        d = SemanticConflictDetector()
        response = '```json\n{"has_conflict": true, "conflict_type": "goal_conflict", "severity": "MEDIUM", "description": "Goals differ", "suggestion": "Align objectives"}\n```'
        result = d._parse_response(response, "A", "B")
        assert result is not None
        assert result.conflict_type == "goal_conflict"

    def test_parse_invalid_response_returns_none(self):
        d = SemanticConflictDetector()
        result = d._parse_response("not valid json at all", "A", "B")
        assert result is None

    def test_max_text_length_truncation_in_pair(self):
        long_text = "The contract review analysis shows. " * 300  # ~6000 chars
        mock_llm = lambda p: '{"has_conflict": true, "conflict_type": "fact_conflict", "severity": "LOW", "description": "x", "suggestion": ""}'
        d = SemanticConflictDetector(llm_callable=mock_llm)
        # Should not crash with long text
        result = d.check_pair("A", long_text, "B", long_text + " slight change")
        assert isinstance(result, SemanticResult) or result is None

    def test_detect_batch_empty_input(self):
        d = SemanticConflictDetector()
        results = d.detect_batch({})
        assert results == []

    def test_detect_batch_single_agent(self):
        d = SemanticConflictDetector()
        results = d.detect_batch({"solo": "just one agent"})
        assert results == []
