"""
Redis state store for shared state across multiple server instances.

Handles:
- Circuit breaker cumulative cost (so budget state survives server restart)
- Agent heartbeat state (shared across server instances behind a load balancer)
- General key-value with TTL for distributed locking and caching

Activated when REDIS_URL env var is set. Falls back to in-memory dict otherwise.

Usage:
    store = get_state_store()
    store.set("budget:ws-1", json.dumps({"current_usd": 42.50}), ttl=3600)
    data = store.get("budget:ws-1")
"""

from __future__ import annotations

import json
import os
import threading
import time


class StateStore:
    """Abstract state store interface."""

    def get(self, key: str) -> str | None:
        raise NotImplementedError

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def incr(self, key: str, amount: float = 1.0) -> float:
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def keys(self, pattern: str) -> list[str]:
        raise NotImplementedError

    def health(self) -> bool:
        raise NotImplementedError


class MemoryStore(StateStore):
    """In-process dict store. Used when Redis is not configured."""

    def __init__(self):
        self._data: dict[str, tuple[float, str]] = {}  # key -> (expires_at, value)
        self._lock = threading.Lock()

    def _purge_expired(self, key: str):
        with self._lock:
            if key in self._data:
                expires, _ = self._data[key]
                if expires > 0 and time.monotonic() > expires:
                    del self._data[key]

    def get(self, key: str) -> str | None:
        self._purge_expired(key)
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            expires, value = entry
            if expires > 0 and time.monotonic() > expires:
                del self._data[key]
                return None
            return value

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        expires = time.monotonic() + ttl if ttl else 0
        with self._lock:
            self._data[key] = (expires, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def incr(self, key: str, amount: float = 1.0) -> float:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self._data[key] = (0, str(amount))
                return amount
            expires, val = entry
            new_val = float(val) + amount
            self._data[key] = (expires, str(new_val))
            return new_val

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def keys(self, pattern: str) -> list[str]:
        result = []
        with self._lock:
            for k in list(self._data.keys()):
                if pattern == "*" or pattern in k:
                    expires, _ = self._data[k]
                    if expires == 0 or time.monotonic() <= expires:
                        result.append(k)
        return result

    def health(self) -> bool:
        return True


class RedisStore(StateStore):
    """Redis-backed state store for multi-instance deployments."""

    def __init__(self, url: str):
        import redis
        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._client.ping()  # fail fast

    def get(self, key: str) -> str | None:
        return self._client.get(key)

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        if ttl:
            self._client.setex(key, ttl, value)
        else:
            self._client.set(key, value)

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def incr(self, key: str, amount: float = 1.0) -> float:
        return self._client.incrbyfloat(key, amount)

    def exists(self, key: str) -> bool:
        return bool(self._client.exists(key))

    def keys(self, pattern: str) -> list[str]:
        return self._client.keys(pattern)

    def health(self) -> bool:
        try:
            return self._client.ping()
        except Exception:
            return False


# ── Module-level singleton ──────────────────────────────────────

_store: StateStore | None = None


def get_state_store() -> StateStore:
    global _store
    if _store is not None:
        return _store

    redis_url = os.environ.get("REDIS_URL", "")
    if redis_url:
        try:
            _store = RedisStore(redis_url)
            return _store
        except Exception:
            pass  # fall through to memory store

    _store = MemoryStore()
    return _store


# ── Convenience helpers for budget / heartbeat ──────────────────

def get_budget_state(workspace_id: str) -> dict | None:
    """Get budget state from shared store."""
    store = get_state_store()
    raw = store.get(f"budget:{workspace_id}")
    if raw:
        return json.loads(raw)
    return None


def set_budget_state(workspace_id: str, data: dict, ttl: int = 86400) -> None:
    """Persist budget state to shared store."""
    store = get_state_store()
    store.set(f"budget:{workspace_id}", json.dumps(data), ttl=ttl)


def incr_budget_current(workspace_id: str, amount: float) -> float:
    """Atomically increment budget current_usd."""
    store = get_state_store()
    return store.incr(f"budget:{workspace_id}:current", amount)


def get_heartbeat_state(agent_name: str, workspace_id: str = "") -> dict | None:
    """Get agent heartbeat from shared store."""
    store = get_state_store()
    raw = store.get(f"heartbeat:{workspace_id}:{agent_name}")
    if raw:
        return json.loads(raw)
    return None


def set_heartbeat_state(agent_name: str, status: str, latency_ms: float,
                        workspace_id: str = "", ttl: int = 600) -> None:
    """Persist agent heartbeat to shared store."""
    store = get_state_store()
    import datetime
    data = {
        "agent_name": agent_name,
        "status": status,
        "latency_ms": latency_ms,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    store.set(f"heartbeat:{workspace_id}:{agent_name}", json.dumps(data), ttl=ttl)
