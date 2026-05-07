"""
Memory Sharing — 跨 Agent 共享记忆池

特性:
  Namespace 隔离 — 不同团队/项目独立空间
  write/read/search — 键值存储 + 子串搜索 + 标签过滤
  TTL 过期 — 自动清理过期条目
  Access tracking — 读取计数
  "学一次，全员受益" 的跨Agent知识共享

用法:
  mem = MemorySharing()
  mem.write("legal", "contract_risks", "违约责任必须明确", source_agent="Analyst", tags=["contract"])
  entry = mem.read("legal", "contract_risks")
  results = mem.search("legal", tags=["contract"], query="违约")
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


# ── Data classes ────────────────────────────────────────────────

@dataclass
class MemoryEntry:
    namespace: str
    key: str
    value: str
    source_agent: str
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float | None = None    # None = never expires
    access_count: int = 0

    @property
    def expired(self) -> bool:
        if self.ttl_seconds is None:
            return False
        return time.time() > self.created_at + self.ttl_seconds

    def to_dict(self) -> dict:
        return {
            "namespace": self.namespace,
            "key": self.key,
            "value": self.value,
            "source_agent": self.source_agent,
            "tags": self.tags,
            "created_at": self.created_at,
            "ttl_seconds": self.ttl_seconds,
            "access_count": self.access_count,
            "expired": self.expired,
        }


# ── MemorySharing ───────────────────────────────────────────────

class MemorySharing:
    def __init__(self):
        self._store: dict[str, dict[str, MemoryEntry]] = {}  # namespace → {key → entry}

    # ── Write ─────────────────────────────────────────────────

    def write(
        self, namespace: str, key: str, value: str,
        source_agent: str = "", tags: list[str] | None = None,
        ttl_seconds: float | None = None,
    ) -> MemoryEntry:
        if namespace not in self._store:
            self._store[namespace] = {}
        entry = MemoryEntry(
            namespace=namespace, key=key, value=value,
            source_agent=source_agent, tags=tags or [],
            ttl_seconds=ttl_seconds,
        )
        self._store[namespace][key] = entry
        return entry

    # ── Read ──────────────────────────────────────────────────

    def read(self, namespace: str, key: str) -> MemoryEntry | None:
        ns = self._store.get(namespace)
        if ns is None:
            return None
        entry = ns.get(key)
        if entry is None:
            return None
        if entry.expired:
            del ns[key]
            if not ns:
                del self._store[namespace]
            return None
        entry.access_count += 1
        return entry

    # ── Search ────────────────────────────────────────────────

    def search(
        self, namespace: str, *, query: str = "",
        tags: list[str] | None = None,
    ) -> list[MemoryEntry]:
        namespaces = (
            list(self._store.keys()) if namespace == "*"
            else [namespace]
        )

        results: list[MemoryEntry] = []
        for ns_name in namespaces:
            ns = self._store.get(ns_name)
            if ns is None:
                continue
            for entry in list(ns.values()):
                if entry.expired:
                    del ns[entry.key]
                    continue
                # Tag filter: entry must have ALL requested tags
                if tags:
                    if not all(t in entry.tags for t in tags):
                        continue
                # Query filter: substring match on key or value
                if query:
                    if query not in entry.key and query not in entry.value:
                        continue
                results.append(entry)

        return results

    # ── Delete ────────────────────────────────────────────────

    def delete(self, namespace: str, key: str) -> bool:
        ns = self._store.get(namespace)
        if ns is None or key not in ns:
            return False
        del ns[key]
        if not ns:
            del self._store[namespace]
        return True

    # ── Namespace Management ──────────────────────────────────

    def list_namespaces(self) -> list[str]:
        # Clean expired namespaces
        self._gc_expired()
        return sorted(self._store.keys())

    def get_namespace(self, namespace: str) -> list[MemoryEntry] | None:
        ns = self._store.get(namespace)
        if ns is None:
            return None
        self._gc_expired()
        if namespace not in self._store:
            return None
        return list(self._store[namespace].values())

    def clear_namespace(self, namespace: str):
        self._store.pop(namespace, None)

    # ── Stats ─────────────────────────────────────────────────

    def get_stats(self) -> dict:
        self._gc_expired()
        total = 0
        by_ns: dict[str, int] = {}
        by_agent: dict[str, int] = {}
        for ns_name, ns in self._store.items():
            count = len(ns)
            total += count
            by_ns[ns_name] = count
            for entry in ns.values():
                agent = entry.source_agent or "unknown"
                by_agent[agent] = by_agent.get(agent, 0) + 1

        return {
            "total_entries": total,
            "namespace_count": len(self._store),
            "by_namespace": by_ns,
            "by_agent": by_agent,
        }

    # ── Internal ──────────────────────────────────────────────

    def _gc_expired(self):
        for ns_name in list(self._store.keys()):
            ns = self._store[ns_name]
            for key in list(ns.keys()):
                if ns[key].expired:
                    del ns[key]
            if not ns:
                del self._store[ns_name]

    # ── Admin ─────────────────────────────────────────────────

    def reset(self):
        self._store.clear()


# ── Module-level convenience ────────────────────────────────────

_memory_sharing: MemorySharing | None = None


def get_memory_sharing() -> MemorySharing:
    global _memory_sharing
    if _memory_sharing is None:
        _memory_sharing = MemorySharing()
    return _memory_sharing


def shared_memory_write(
    namespace: str, key: str, value: str,
    source_agent: str = "", tags: list[str] | None = None,
    ttl_seconds: float | None = None,
) -> MemoryEntry:
    return get_memory_sharing().write(
        namespace, key, value, source_agent=source_agent,
        tags=tags, ttl_seconds=ttl_seconds,
    )


def shared_memory_read(namespace: str, key: str) -> MemoryEntry | None:
    return get_memory_sharing().read(namespace, key)
