"""Memory Sharing 测试 — 跨Agent共享记忆池"""

import time

import pytest

from ahy_governance import (
    MemorySharing,
    MemoryEntry,
    get_memory_sharing,
    shared_memory_write,
    shared_memory_read,
)


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def ms():
    m = MemorySharing()
    yield m
    m.reset()


@pytest.fixture
def populated_ms(ms):
    ms.write("legal_knowledge", "contract_risk_clause",
             "违约责任条款必须明确赔偿金额和计算方式",
             source_agent="LegalAnalyst", tags=["contract", "risk"])
    ms.write("legal_knowledge", "ndf_template",
             "保密协议模板：期限不超过5年，范围覆盖甲乙双方",
             source_agent="DocGenerator", tags=["nda", "template"])
    ms.write("math_rules", "pi_value",
             "3.141592653589793", source_agent="Calculator", tags=["constant"])
    return ms


# ── Write/Read Tests ────────────────────────────────────────────

class TestWriteRead:
    def test_write_returns_entry(self, ms):
        entry = ms.write("ns1", "key1", "value1", source_agent="AgentA")
        assert isinstance(entry, MemoryEntry)
        assert entry.namespace == "ns1"
        assert entry.key == "key1"
        assert entry.value == "value1"
        assert entry.source_agent == "AgentA"

    def test_read_existing_key(self, populated_ms):
        entry = populated_ms.read("legal_knowledge", "contract_risk_clause")
        assert entry is not None
        assert "违约责任" in entry.value

    def test_read_nonexistent_key(self, ms):
        assert ms.read("no-ns", "no-key") is None

    def test_read_nonexistent_namespace(self, ms):
        assert ms.read("ghost-ns", "any-key") is None

    def test_write_overwrites(self, ms):
        ms.write("ns", "k", "v1", source_agent="A")
        ms.write("ns", "k", "v2", source_agent="B")
        entry = ms.read("ns", "k")
        assert entry.value == "v2"
        assert entry.source_agent == "B"

    def test_write_increments_access_count_on_read(self, populated_ms):
        populated_ms.read("legal_knowledge", "contract_risk_clause")
        populated_ms.read("legal_knowledge", "contract_risk_clause")
        entry = populated_ms.read("legal_knowledge", "contract_risk_clause")
        assert entry.access_count >= 2


# ── Search Tests ────────────────────────────────────────────────

class TestSearch:
    def test_search_by_tag(self, populated_ms):
        results = populated_ms.search("legal_knowledge", tags=["contract"])
        assert len(results) == 1
        assert results[0].key == "contract_risk_clause"

    def test_search_by_multiple_tags(self, populated_ms):
        results = populated_ms.search("legal_knowledge", tags=["nda", "template"])
        assert len(results) == 1

    def test_search_by_query_substring(self, populated_ms):
        results = populated_ms.search("legal_knowledge", query="保密协议")
        assert len(results) == 1
        assert results[0].key == "ndf_template"

    def test_search_no_match(self, populated_ms):
        assert populated_ms.search("legal_knowledge", query="不存在的") == []

    def test_search_empty_namespace(self, ms):
        ms.write("ns", "k", "v", "A")
        # Empty query returns all entries (no filter)
        assert len(ms.search("ns", query="")) == 1
        # Non-empty query filters
        assert ms.search("ns", query="v")[0].key == "k"
        assert ms.search("ns", query="nomatch") == []

    def test_search_across_all_namespaces(self, populated_ms):
        results = populated_ms.search("*", query="3.1415")
        assert len(results) == 1
        assert results[0].namespace == "math_rules"


# ── Namespace Tests ─────────────────────────────────────────────

class TestNamespaces:
    def test_list_namespaces(self, populated_ms):
        namespaces = populated_ms.list_namespaces()
        assert "legal_knowledge" in namespaces
        assert "math_rules" in namespaces
        assert len(namespaces) == 2

    def test_get_namespace(self, populated_ms):
        ns = populated_ms.get_namespace("legal_knowledge")
        assert ns is not None
        assert len(ns) == 2

    def test_clear_namespace(self, populated_ms):
        populated_ms.clear_namespace("legal_knowledge")
        assert "legal_knowledge" not in populated_ms.list_namespaces()
        assert populated_ms.read("legal_knowledge", "contract_risk_clause") is None

    def test_delete_entry(self, populated_ms):
        assert populated_ms.delete("legal_knowledge", "ndf_template")
        assert populated_ms.read("legal_knowledge", "ndf_template") is None

    def test_delete_nonexistent(self, ms):
        assert not ms.delete("no", "no")


# ── TTL Tests ───────────────────────────────────────────────────

class TestTTL:
    def test_ttl_expiration(self, ms):
        ms.write("ns", "ephemeral", "temp data", source_agent="A", ttl_seconds=0)
        assert ms.read("ns", "ephemeral") is None

    def test_ttl_not_expired(self, ms):
        ms.write("ns", "persistent", "data", source_agent="A", ttl_seconds=3600)
        assert ms.read("ns", "persistent") is not None

    def test_ttl_search_excludes_expired(self, ms):
        ms.write("ns", "k1", "expired", source_agent="A", ttl_seconds=0)
        ms.write("ns", "k2", "alive", source_agent="A", ttl_seconds=3600)
        results = ms.search("ns", query="alive")
        assert len(results) == 1

    def test_no_ttl_default(self, ms):
        """Without TTL, entries live forever"""
        ms.write("ns", "forever", "data", source_agent="A")
        assert ms.read("ns", "forever") is not None


# ── Stats Tests ─────────────────────────────────────────────────

class TestStats:
    def test_stats_structure(self, populated_ms):
        stats = populated_ms.get_stats()
        assert stats["total_entries"] == 3
        assert stats["namespace_count"] == 2
        assert "by_namespace" in stats
        assert "by_agent" in stats
        assert stats["by_namespace"]["legal_knowledge"] == 2

    def test_stats_by_agent(self, populated_ms):
        stats = populated_ms.get_stats()
        assert stats["by_agent"]["LegalAnalyst"] == 1
        assert stats["by_agent"]["DocGenerator"] == 1

    def test_stats_empty(self, ms):
        stats = ms.get_stats()
        assert stats["total_entries"] == 0
        assert stats["namespace_count"] == 0


# ── Edge Cases ──────────────────────────────────────────────────

class TestEdgeCases:
    def test_large_value(self, ms):
        big_value = "数据" * 10000
        entry = ms.write("ns", "big", big_value, source_agent="A")
        assert len(entry.value) == len(big_value)

    def test_many_entries(self, ms):
        for i in range(200):
            ms.write("ns", f"key-{i}", f"value-{i}", source_agent=f"Agent{i % 10}")
        assert ms.get_stats()["total_entries"] == 200

    def test_special_characters_key(self, ms):
        ms.write("ns", "key/with:special.chars_123", "value", "A")
        assert ms.read("ns", "key/with:special.chars_123") is not None

    def test_unicode_value(self, ms):
        ms.write("ns", "unicode", "値段は約100円です🎉", source_agent="A")
        entry = ms.read("ns", "unicode")
        assert "🎉" in entry.value

    def test_reset_clears_all(self, populated_ms):
        populated_ms.reset()
        assert populated_ms.get_stats()["total_entries"] == 0
        assert populated_ms.list_namespaces() == []

    def test_entry_to_dict(self, ms):
        entry = ms.write("ns", "k", "v", source_agent="A", tags=["t1"])
        d = entry.to_dict()
        assert d["namespace"] == "ns"
        assert d["key"] == "k"
        assert d["tags"] == ["t1"]


# ── Multi-Agent Sharing Tests ───────────────────────────────────

class TestMultiAgent:
    def test_agents_share_namespace(self, ms):
        ms.write("shared", "k1", "AgentA的发现", source_agent="Analyst")
        ms.write("shared", "k2", "AgentB的发现", source_agent="Reviewer")
        # Both agents can read each other's entries
        a_read = ms.read("shared", "k2")
        assert a_read is not None
        assert "AgentB" in a_read.value

    def test_agent_isolation_by_namespace(self, ms):
        ms.write("agent_a_private", "secret", "A的数据", source_agent="A")
        ms.write("agent_b_private", "secret", "B的数据", source_agent="B")
        assert ms.read("agent_a_private", "secret").value == "A的数据"
        assert ms.read("agent_b_private", "secret").value == "B的数据"


# ── Convenience Functions ───────────────────────────────────────

class TestConvenience:
    def test_get_memory_sharing_singleton(self):
        m1 = get_memory_sharing()
        m2 = get_memory_sharing()
        assert m1 is m2
        m1.reset()

    def test_shared_memory_write_read(self):
        m = get_memory_sharing()
        m.reset()
        shared_memory_write("ns", "k", "v", source_agent="Test")
        entry = shared_memory_read("ns", "k")
        assert entry is not None
        assert entry.value == "v"
        m.reset()
