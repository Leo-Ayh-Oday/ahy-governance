"""Tests for ahy_governance.state_store — MemoryStore and convenience helpers."""

import json
import time
import pytest
from ahy_governance.state_store import (
    StateStore, MemoryStore, RedisStore,
    get_state_store,
    get_budget_state, set_budget_state, incr_budget_current,
    get_heartbeat_state, set_heartbeat_state,
)


# ── MemoryStore ─────────────────────────────────────────────

class TestMemoryStore:
    @pytest.fixture
    def store(self):
        return MemoryStore()

    def test_set_and_get(self, store):
        store.set("k1", "v1")
        assert store.get("k1") == "v1"

    def test_get_nonexistent(self, store):
        assert store.get("nope") is None

    def test_delete(self, store):
        store.set("k1", "v1")
        store.delete("k1")
        assert store.get("k1") is None

    def test_delete_nonexistent(self, store):
        store.delete("nope")  # Should not crash

    def test_incr_new_key(self, store):
        assert store.incr("counter") == 1.0

    def test_incr_existing(self, store):
        store.set("counter", "5")
        assert store.incr("counter", 3.0) == 8.0

    def test_incr_with_amount(self, store):
        store.incr("c", 1.0)
        store.incr("c", 2.5)
        assert store.get("c") == "3.5"

    def test_exists(self, store):
        assert store.exists("k") is False
        store.set("k", "v")
        assert store.exists("k") is True

    def test_keys_wildcard(self, store):
        store.set("a:1", "v1")
        store.set("b:2", "v2")
        store.set("a:3", "v3")
        result = store.keys("*")
        assert len(result) == 3

    def test_keys_pattern(self, store):
        store.set("budget:ws1", "v1")
        store.set("budget:ws2", "v2")
        store.set("heartbeat:a1", "v3")
        result = store.keys("budget")
        assert len(result) == 2

    def test_health(self, store):
        assert store.health() is True

    def test_ttl_expiration(self, store):
        store.set("k", "v", ttl=1)  # 1 second
        assert store.get("k") == "v"
        time.sleep(1.1)
        assert store.get("k") is None

    def test_ttl_no_expiration(self, store):
        store.set("k", "v")  # No TTL
        assert store.get("k") == "v"
        # Should still be there after a bit
        time.sleep(0.1)
        assert store.get("k") == "v"

    def test_keys_with_expired(self, store):
        store.set("k1", "v1", ttl=1)
        store.set("k2", "v2")  # No TTL
        time.sleep(1.1)
        result = store.keys("*")
        assert "k2" in result
        assert "k1" not in result

    def test_overwrite(self, store):
        store.set("k", "v1")
        store.set("k", "v2")
        assert store.get("k") == "v2"

    def test_incr_expired_key(self, store):
        store.set("k", "5", ttl=1)
        time.sleep(1.1)
        # incr doesn't check expiry — it reads from _data directly
        # so it will still see the old value and add to it
        result = store.incr("k", 3.0)
        assert result == 8.0  # 5 + 3


# ── Convenience helpers ─────────────────────────────────────

class TestConvenienceHelpers:
    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        import ahy_governance.state_store as mod
        mod._store = None
        yield
        mod._store = None

    def test_set_and_get_budget_state(self):
        set_budget_state("ws1", {"current_usd": 42.5})
        data = get_budget_state("ws1")
        assert data is not None
        assert data["current_usd"] == 42.5

    def test_get_budget_state_none(self):
        assert get_budget_state("nonexistent") is None

    def test_incr_budget_current(self):
        set_budget_state("ws2", {"current_usd": 0})
        v1 = incr_budget_current("ws2", 10.0)
        assert v1 == 10.0
        v2 = incr_budget_current("ws2", 5.5)
        assert v2 == 15.5

    def test_set_and_get_heartbeat_state(self):
        set_heartbeat_state("Planner", "ok", 120.0)
        data = get_heartbeat_state("Planner")
        assert data is not None
        assert data["agent_name"] == "Planner"
        assert data["status"] == "ok"
        assert data["latency_ms"] == 120.0

    def test_get_heartbeat_state_none(self):
        assert get_heartbeat_state("Nobody") is None

    def test_heartbeat_with_workspace(self):
        set_heartbeat_state("A", "ok", 100, workspace_id="ws1")
        set_heartbeat_state("A", "degraded", 200, workspace_id="ws2")
        assert get_heartbeat_state("A", "ws1")["status"] == "ok"
        assert get_heartbeat_state("A", "ws2")["status"] == "degraded"


# ── Singleton ───────────────────────────────────────────────

class TestSingleton:
    def test_returns_memory_store(self):
        import ahy_governance.state_store as mod
        mod._store = None
        store = get_state_store()
        assert isinstance(store, MemoryStore)
        mod._store = None

    def test_returns_same_instance(self):
        import ahy_governance.state_store as mod
        mod._store = None
        s1 = get_state_store()
        s2 = get_state_store()
        assert s1 is s2
        mod._store = None

    def test_redis_fallback(self, monkeypatch):
        """When REDIS_URL is set but redis fails, fall back to memory."""
        import ahy_governance.state_store as mod
        mod._store = None
        monkeypatch.setenv("REDIS_URL", "redis://localhost:99999")
        store = get_state_store()
        assert isinstance(store, MemoryStore)
        mod._store = None


# ── Abstract interface ──────────────────────────────────────

class TestAbstractInterface:
    def test_abstract_methods_raise(self):
        store = StateStore()
        with pytest.raises(NotImplementedError):
            store.get("k")
        with pytest.raises(NotImplementedError):
            store.set("k", "v")
        with pytest.raises(NotImplementedError):
            store.delete("k")
        with pytest.raises(NotImplementedError):
            store.incr("k")
        with pytest.raises(NotImplementedError):
            store.exists("k")
        with pytest.raises(NotImplementedError):
            store.keys("*")
        with pytest.raises(NotImplementedError):
            store.health()
