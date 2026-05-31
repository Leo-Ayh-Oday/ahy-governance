"""Tests for SDK Decorator — 一行集成装饰器."""

import pytest
import asyncio

from ahy_governance.decorator import track, _estimate_tokens, OUTPUT_MAX_LEN
from ahy_governance.cost_tracker import get_tracker


# ── Token estimation ────────────────────────────────────────────

class TestTokenEstimation:
    def test_empty_string(self):
        assert _estimate_tokens("") == 1

    def test_short_string(self):
        assert _estimate_tokens("hello") == 1

    def test_long_string(self):
        # 100 chars / 4 = 25 tokens
        assert _estimate_tokens("a" * 100) == 25


# ── Sync function tracking ──────────────────────────────────────

class TestSyncDecorator:
    def test_tracks_basic_call(self):
        """Decorator should not raise and should return original result."""
        @track(agent="TestAgent", model="gpt-4o")
        def add(a: int, b: int) -> int:
            return a + b

        result = add(2, 3)
        assert result == 5

    def test_tracks_with_session(self):
        @track(agent="TestAgent", model="gpt-4o", session_id="sess-1")
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        result = greet("World")
        assert result == "Hello, World!"

    def test_preserves_exception(self):
        """Decorator should re-raise exceptions from the wrapped function."""
        @track(agent="TestAgent", model="gpt-4o")
        def fail():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            fail()

    def test_output_capture_disabled(self):
        @track(agent="TestAgent", capture_output=False)
        def compute() -> str:
            return "x" * 1000

        result = compute()
        assert result == "x" * 1000

    def test_output_truncated(self):
        @track(agent="TestAgent", output_max_len=10)
        def long_output() -> str:
            return "a" * 1000

        result = long_output()
        assert result == "a" * 1000  # original result is not truncated

    def test_preserves_function_name(self):
        @track(agent="TestAgent")
        def my_function():
            pass

        assert my_function.__name__ == "my_function"


# ── Async function tracking ─────────────────────────────────────

class TestAsyncDecorator:
    @pytest.mark.anyio
    async def test_tracks_async_call(self):
        @track(agent="AsyncAgent", model="gpt-4o")
        async def compute(x: int) -> int:
            return x * 2

        result = await compute(21)
        assert result == 42

    @pytest.mark.anyio
    async def test_async_preserves_exception(self):
        @track(agent="AsyncAgent")
        async def fail():
            raise RuntimeError("async boom")

        with pytest.raises(RuntimeError, match="async boom"):
            await fail()

    @pytest.mark.anyio
    async def test_async_preserves_function_name(self):
        @track(agent="AsyncAgent")
        async def my_async_func():
            pass

        assert my_async_func.__name__ == "my_async_func"


# ── Cost tracking integration ───────────────────────────────────

class TestCostTracking:
    def test_records_cost_entry(self):
        """Decorator should record a cost entry via CostTracker."""
        tracker = get_tracker()
        tracker.reset()
        initial_count = tracker.entry_count

        @track(agent="CostTestAgent", model="gpt-4o")
        def work(prompt: str) -> str:
            return "response"

        work("test prompt with some tokens")

        assert tracker.entry_count > initial_count
