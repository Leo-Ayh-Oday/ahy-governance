"""Tests for Auto Resolver — 冲突自动修复引擎."""

import pytest
from dataclasses import dataclass

from ahy_governance.auto_resolver import (
    AutoResolver,
    Resolution,
    ResolutionStatus,
    ResolutionStrategy,
    auto_resolve,
    get_resolver,
)
from ahy_governance.conflict_detector import (
    Conflict,
    ConflictType,
    Severity,
)


# ── Helpers ─────────────────────────────────────────────────────

@dataclass
class FakeResult:
    output: dict


def _fact_conflict(agent_a="Planner", agent_b="Analyst", attr="amount") -> Conflict:
    return Conflict(
        conflict_type=ConflictType.FACT_CONFLICT,
        severity=Severity.HIGH,
        agents_involved=[agent_a, agent_b],
        description=f"属性 '{attr}' 值矛盾",
        evidence={"attribute": attr},
    )


_SENTINEL = object()

def _dep_break(upstream="Planner", downstream="Writer", missing=_SENTINEL) -> Conflict:
    return Conflict(
        conflict_type=ConflictType.DEPENDENCY_BREAK,
        severity=Severity.CRITICAL,
        agents_involved=[upstream, downstream],
        description=f"{downstream} 依赖 {upstream} 的字段缺失",
        evidence={"missing_fields": ["contract_text", "risk_score"] if missing is _SENTINEL else missing},
    )


def _format_mismatch(upstream="Planner", downstream="Writer", field="count", expected="integer") -> Conflict:
    return Conflict(
        conflict_type=ConflictType.FORMAT_MISMATCH,
        severity=Severity.HIGH,
        agents_involved=[upstream, downstream],
        description=f"字段 '{field}' 类型不匹配",
        evidence={"field": field, "expected": expected, "actual": "string"},
    )


# ── Fact conflict resolution ───────────────────────────────────

class TestFactConflictResolution:
    def test_high_confidence_picked(self):
        """Higher confidence agent's value should be picked."""
        conflict = _fact_conflict()
        outputs = {
            "Planner": FakeResult({"amount": "100万", "confidence": 0.95}),
            "Analyst": FakeResult({"amount": "200万", "confidence": 0.3}),
        }
        resolver = AutoResolver(min_confidence=0.7)
        results = resolver.resolve([conflict], outputs)

        assert len(results) == 1
        r = results[0]
        assert r.status == ResolutionStatus.RESOLVED
        assert r.strategy == ResolutionStrategy.HIGH_CONFIDENCE_PICK
        assert r.evidence["winning_agent"] == "Planner"
        assert r.evidence["losing_agent"] == "Analyst"

    def test_both_below_threshold_escalated(self):
        """Both agents below min_confidence → escalated."""
        conflict = _fact_conflict()
        outputs = {
            "Planner": FakeResult({"amount": "100万", "confidence": 0.4}),
            "Analyst": FakeResult({"amount": "200万", "confidence": 0.3}),
        }
        resolver = AutoResolver(min_confidence=0.7)
        results = resolver.resolve([conflict], outputs)

        assert results[0].status == ResolutionStatus.ESCALATED

    def test_no_confidence_escalated(self):
        """No confidence field → escalated."""
        conflict = _fact_conflict()
        outputs = {
            "Planner": FakeResult({"amount": "100万"}),
            "Analyst": FakeResult({"amount": "200万"}),
        }
        resolver = AutoResolver(min_confidence=0.7)
        results = resolver.resolve([conflict], outputs)

        assert results[0].status == ResolutionStatus.ESCALATED

    def test_missing_agent_escalated(self):
        """Only one agent in outputs → escalated."""
        conflict = _fact_conflict()
        outputs = {
            "Planner": FakeResult({"amount": "100万", "confidence": 0.95}),
        }
        resolver = AutoResolver()
        results = resolver.resolve([conflict], outputs)

        assert results[0].status == ResolutionStatus.ESCALATED


# ── Dependency break resolution ────────────────────────────────

class TestDependencyBreakResolution:
    def test_returns_retrigger_hint(self):
        """Should return a re-trigger hint with missing fields."""
        conflict = _dep_break(missing=["contract_text", "risk_score"])
        outputs = {
            "Planner": FakeResult({"summary": "ok"}),
            "Writer": FakeResult({"report": "pending"}),
        }
        resolver = AutoResolver()
        results = resolver.resolve([conflict], outputs)

        r = results[0]
        assert r.status == ResolutionStatus.RESOLVED
        assert r.strategy == ResolutionStrategy.RE_TRIGGER_UPSTREAM
        assert "contract_text" in r.resolution_detail
        assert r.evidence["upstream_agent"] == "Planner"
        assert r.evidence["missing_fields"] == ["contract_text", "risk_score"]
        assert "re_trigger_hint" in r.evidence

    def test_no_missing_fields_escalated(self):
        """Empty missing_fields → escalated."""
        conflict = _dep_break(missing=[])
        outputs = {"Planner": FakeResult({}), "Writer": FakeResult({})}
        resolver = AutoResolver()
        results = resolver.resolve([conflict], outputs)

        assert results[0].status == ResolutionStatus.ESCALATED


# ── Format mismatch resolution ─────────────────────────────────

class TestFormatMismatchResolution:
    def test_str_to_int_conversion(self):
        """String "42" → integer 42."""
        conflict = _format_mismatch(field="count", expected="integer")
        outputs = {
            "Planner": FakeResult({"count": "42", "name": "test"}),
            "Writer": FakeResult({}),
        }
        resolver = AutoResolver()
        results = resolver.resolve([conflict], outputs)

        r = results[0]
        assert r.status == ResolutionStatus.RESOLVED
        assert r.strategy == ResolutionStrategy.AUTO_TYPE_CONVERT
        assert r.evidence["converted_value"] == 42

    def test_str_to_float_conversion(self):
        """String "3.14" → float 3.14."""
        conflict = _format_mismatch(field="score", expected="number")
        outputs = {
            "Planner": FakeResult({"score": "3.14"}),
            "Writer": FakeResult({}),
        }
        resolver = AutoResolver()
        results = resolver.resolve([conflict], outputs)

        r = results[0]
        assert r.status == ResolutionStatus.RESOLVED
        assert r.evidence["converted_value"] == 3.14

    def test_invalid_conversion_escalated(self):
        """String "abc" → integer should fail."""
        conflict = _format_mismatch(field="count", expected="integer")
        outputs = {
            "Planner": FakeResult({"count": "abc"}),
            "Writer": FakeResult({}),
        }
        resolver = AutoResolver()
        results = resolver.resolve([conflict], outputs)

        assert results[0].status == ResolutionStatus.ESCALATED

    def test_int_to_str_conversion(self):
        """Integer 42 → string "42"."""
        conflict = _format_mismatch(field="code", expected="string")
        outputs = {
            "Planner": FakeResult({"code": 42}),
            "Writer": FakeResult({}),
        }
        resolver = AutoResolver()
        results = resolver.resolve([conflict], outputs)

        r = results[0]
        assert r.status == ResolutionStatus.RESOLVED
        assert r.evidence["converted_value"] == "42"

    def test_str_to_bool_conversion(self):
        """String "true" → boolean True."""
        conflict = _format_mismatch(field="active", expected="boolean")
        outputs = {
            "Planner": FakeResult({"active": "true"}),
            "Writer": FakeResult({}),
        }
        resolver = AutoResolver()
        results = resolver.resolve([conflict], outputs)

        r = results[0]
        assert r.status == ResolutionStatus.RESOLVED
        assert r.evidence["converted_value"] is True

    def test_missing_field_escalated(self):
        """Field not in output → escalated."""
        conflict = _format_mismatch(field="nonexistent", expected="integer")
        outputs = {
            "Planner": FakeResult({"other_field": "42"}),
            "Writer": FakeResult({}),
        }
        resolver = AutoResolver()
        results = resolver.resolve([conflict], outputs)

        assert results[0].status == ResolutionStatus.ESCALATED


# ── Unsupported conflict types ─────────────────────────────────

class TestUnsupportedTypes:
    def test_scope_overlap_skipped(self):
        conflict = Conflict(
            conflict_type=ConflictType.SCOPE_OVERLAP,
            severity=Severity.MEDIUM,
            agents_involved=["A", "B"],
            description="overlap",
        )
        resolver = AutoResolver()
        results = resolver.resolve([conflict], {})

        assert results[0].status == ResolutionStatus.SKIPPED

    def test_confidence_clash_skipped(self):
        conflict = Conflict(
            conflict_type=ConflictType.CONFIDENCE_CLASH,
            severity=Severity.HIGH,
            agents_involved=["A", "B"],
            description="clash",
        )
        resolver = AutoResolver()
        results = resolver.resolve([conflict], {})

        assert results[0].status == ResolutionStatus.SKIPPED


# ── Mixed conflict list ────────────────────────────────────────

class TestMixedResolution:
    def test_mixed_conflicts(self):
        """Resolve a mix of conflict types at once."""
        conflicts = [
            _fact_conflict(),
            _dep_break(missing=["field_a"]),
            _format_mismatch(field="count", expected="integer"),
        ]
        outputs = {
            "Planner": FakeResult({
                "amount": "100万", "confidence": 0.95, "count": "42",
            }),
            "Analyst": FakeResult({"amount": "200万", "confidence": 0.3}),
            "Writer": FakeResult({}),
        }
        resolver = AutoResolver(min_confidence=0.7)
        results = resolver.resolve(conflicts, outputs)

        assert len(results) == 3
        statuses = {r.status for r in results}
        assert ResolutionStatus.RESOLVED in statuses

    def test_empty_conflicts(self):
        resolver = AutoResolver()
        results = resolver.resolve([], {})
        assert results == []


# ── Resolution dataclass ───────────────────────────────────────

class TestResolutionDataclass:
    def test_to_dict(self):
        r = Resolution(
            conflict_type=ConflictType.FACT_CONFLICT,
            strategy=ResolutionStrategy.HIGH_CONFIDENCE_PICK,
            status=ResolutionStatus.RESOLVED,
            original_agents=["A", "B"],
            resolution_detail="picked A",
            confidence=0.95,
        )
        d = r.to_dict()
        assert d["conflict_type"] == "fact_conflict"
        assert d["status"] == "resolved"
        assert d["confidence"] == 0.95


# ── Singleton and convenience ──────────────────────────────────

class TestSingleton:
    def test_get_resolver_returns_singleton(self):
        r1 = get_resolver()
        r2 = get_resolver()
        assert r1 is r2

    def test_auto_resolve_convenience(self):
        results = auto_resolve([], {})
        assert results == []
