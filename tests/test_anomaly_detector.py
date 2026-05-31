"""Tests for Anomaly Detector — Agent 行为异常检测引擎."""

import time
from datetime import datetime, timezone, timedelta

import pytest

from ahy_governance.anomaly_detector import (
    Anomaly,
    AnomalyDetector,
    AnomalyType,
    _mean,
    _stddev,
    _parse_timestamp,
    get_anomaly_detector,
    detect_anomalies,
)
from ahy_governance.conflict_detector import Severity
from ahy_governance.cost_tracker import CostTracker, CostEntry
from ahy_governance.health_monitor import HealthMonitor


# ── Helper: mock health monitor ─────────────────────────────────

def _make_health_monitor(agent_calls: dict[str, list[dict]]) -> HealthMonitor:
    """Create a HealthMonitor with pre-populated call data."""
    hm = HealthMonitor()
    hm._calls = agent_calls
    return hm


def _make_cost_tracker(entries: list[CostEntry]) -> CostTracker:
    """Create a CostTracker with pre-populated entries."""
    ct = CostTracker()
    ct._entries = entries
    return ct


def _ts(minutes_ago: int) -> str:
    """ISO timestamp N minutes ago."""
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


# ── Stats helpers ───────────────────────────────────────────────

class TestStatsHelpers:
    def test_mean_empty(self):
        assert _mean([]) == 0.0

    def test_mean_single(self):
        assert _mean([5.0]) == 5.0

    def test_mean_multiple(self):
        assert _mean([1.0, 2.0, 3.0]) == 2.0

    def test_stddev_empty(self):
        assert _stddev([]) == 0.0

    def test_stddev_single(self):
        assert _stddev([5.0]) == 0.0

    def test_stddev_multiple(self):
        val = _stddev([1.0, 2.0, 3.0])
        assert val > 0
        assert abs(val - 1.0) < 0.01

    def test_parse_timestamp_valid(self):
        ts = "2026-01-15T10:30:00+00:00"
        result = _parse_timestamp(ts)
        assert isinstance(result, float)
        assert result > 0

    def test_parse_timestamp_invalid(self):
        result = _parse_timestamp("not-a-date")
        assert isinstance(result, float)


# ── Anomaly dataclass ──────────────────────────────────────────

class TestAnomaly:
    def test_to_dict(self):
        a = Anomaly(
            anomaly_type=AnomalyType.TOKEN_SPIKE,
            agent_name="Planner",
            severity=Severity.HIGH,
            description="Token spike detected",
            current_value=50000,
            baseline_value=5000,
            threshold=50000,
        )
        d = a.to_dict()
        assert d["type"] == "token_spike"
        assert d["agent"] == "Planner"
        assert d["severity"] == "HIGH"
        assert d["current_value"] == 50000


# ── Token spike detection ──────────────────────────────────────

class TestTokenSpikeDetection:
    def test_no_spike_normal_usage(self):
        """Normal usage should not trigger anomaly."""
        ct = _make_cost_tracker([
            CostEntry("Planner", "gpt-4o", 1000, 500, 0.01, "s1", _ts(i))
            for i in range(20, 0, -1)
        ])
        det = AnomalyDetector(token_spike_multiplier=10.0, min_data_points=3)
        anomalies = det.scan_token_spikes(ct)
        assert len(anomalies) == 0

    def test_spike_detected(self):
        """Recent entries with 20x tokens should trigger."""
        entries = [
            CostEntry("Planner", "gpt-4o", 1000, 500, 0.01, "s1", _ts(i))
            for i in range(20, 4, -1)
        ]
        # Recent entries: 20x tokens
        entries.extend([
            CostEntry("Planner", "gpt-4o", 20000, 10000, 0.15, "s1", _ts(i))
            for i in range(4, 0, -1)
        ])
        ct = _make_cost_tracker(entries)
        det = AnomalyDetector(token_spike_multiplier=10.0, min_data_points=3)
        anomalies = det.scan_token_spikes(ct)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == AnomalyType.TOKEN_SPIKE
        assert anomalies[0].agent_name == "Planner"

    def test_below_threshold_no_spike(self):
        """5x tokens with 10x threshold should NOT trigger."""
        entries = [
            CostEntry("Planner", "gpt-4o", 1000, 500, 0.01, "s1", _ts(i))
            for i in range(20, 4, -1)
        ]
        entries.extend([
            CostEntry("Planner", "gpt-4o", 4000, 2000, 0.03, "s1", _ts(i))
            for i in range(4, 0, -1)
        ])
        ct = _make_cost_tracker(entries)
        det = AnomalyDetector(token_spike_multiplier=10.0, min_data_points=3)
        anomalies = det.scan_token_spikes(ct)
        assert len(anomalies) == 0

    def test_insufficient_data_skipped(self):
        """Too few data points should be skipped."""
        ct = _make_cost_tracker([
            CostEntry("Planner", "gpt-4o", 1000, 500, 0.01, "s1", _ts(1)),
        ])
        det = AnomalyDetector(min_data_points=5)
        anomalies = det.scan_token_spikes(ct)
        assert len(anomalies) == 0

    def test_trivial_usage_skipped(self):
        """Agents with < 100 baseline tokens should be skipped."""
        entries = [
            CostEntry("Tiny", "gpt-4o-mini", 10, 5, 0.0001, "s1", _ts(i))
            for i in range(20, 4, -1)
        ]
        entries.extend([
            CostEntry("Tiny", "gpt-4o-mini", 500, 200, 0.003, "s1", _ts(i))
            for i in range(4, 0, -1)
        ])
        ct = _make_cost_tracker(entries)
        det = AnomalyDetector(token_spike_multiplier=10.0, min_data_points=3)
        anomalies = det.scan_token_spikes(ct)
        assert len(anomalies) == 0

    def test_empty_tracker(self):
        ct = _make_cost_tracker([])
        det = AnomalyDetector()
        assert det.scan_token_spikes(ct) == []


# ── Repeated calls detection ───────────────────────────────────

class TestRepeatedCallsDetection:
    def test_normal_call_count(self):
        calls = {"Planner": [{"success": True, "latency_ms": 100}] * 10}
        hm = _make_health_monitor(calls)
        det = AnomalyDetector(repeated_calls_per_minute=50)
        anomalies = det.scan_repeated_calls(hm)
        assert len(anomalies) == 0

    def test_excessive_calls_detected(self):
        calls = {"Planner": [{"success": True, "latency_ms": 100}] * 100}
        hm = _make_health_monitor(calls)
        det = AnomalyDetector(repeated_calls_per_minute=50)
        anomalies = det.scan_repeated_calls(hm)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == AnomalyType.REPEATED_CALLS

    def test_two_agents_one_anomaly(self):
        calls = {
            "Planner": [{"success": True, "latency_ms": 100}] * 10,
            "Spammer": [{"success": True, "latency_ms": 100}] * 200,
        }
        hm = _make_health_monitor(calls)
        det = AnomalyDetector(repeated_calls_per_minute=50)
        anomalies = det.scan_repeated_calls(hm)
        assert len(anomalies) == 1
        assert anomalies[0].agent_name == "Spammer"

    def test_empty_monitor(self):
        hm = _make_health_monitor({})
        det = AnomalyDetector()
        assert det.scan_repeated_calls(hm) == []


# ── Success rate drop detection ─────────────────────────────────

class TestSuccessRateDropDetection:
    def test_stable_rate_no_anomaly(self):
        calls = {"Planner": [{"success": True, "latency_ms": 100}] * 20}
        hm = _make_health_monitor(calls)
        det = AnomalyDetector(min_data_points=3)
        anomalies = det.scan_success_rate_drop(hm)
        assert len(anomalies) == 0

    def test_rate_drop_detected(self):
        # Baseline: all success; Recent: all failure
        call_list = [{"success": True, "latency_ms": 100}] * 16
        call_list += [{"success": False, "latency_ms": 5000}] * 4
        calls = {"Planner": call_list}
        hm = _make_health_monitor(calls)
        det = AnomalyDetector(
            success_rate_drop_threshold=0.20,
            min_data_points=3,
        )
        anomalies = det.scan_success_rate_drop(hm)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == AnomalyType.SUCCESS_RATE_DROP
        assert anomalies[0].current_value == 0.0  # 0% recent success

    def test_small_drop_no_anomaly(self):
        # 90% → 80% = 10% drop, threshold is 20%
        call_list = [{"success": True}] * 18 + [{"success": False}] * 2
        call_list += [{"success": True}] * 4 + [{"success": False}] * 1
        calls = {"Planner": call_list}
        hm = _make_health_monitor(calls)
        det = AnomalyDetector(
            success_rate_drop_threshold=0.20,
            min_data_points=3,
        )
        anomalies = det.scan_success_rate_drop(hm)
        # 10% drop < 20% threshold → no anomaly
        assert len(anomalies) == 0

    def test_insufficient_data(self):
        calls = {"Planner": [{"success": True}]}
        hm = _make_health_monitor(calls)
        det = AnomalyDetector(min_data_points=5)
        assert det.scan_success_rate_drop(hm) == []


# ── Output length anomaly detection ────────────────────────────

class TestOutputLengthAnomaly:
    def test_normal_length_no_anomaly(self):
        calls = {
            "Planner": [
                {"success": True, "latency_ms": 100, "output_length": 100}
                for _ in range(20)
            ]
        }
        hm = _make_health_monitor(calls)
        det = AnomalyDetector(output_length_multiplier=5.0, min_data_points=3)
        anomalies = det.scan_output_length_anomaly(hm)
        assert len(anomalies) == 0

    def test_length_spike_detected(self):
        call_list = [
            {"success": True, "latency_ms": 100, "output_length": 100}
            for _ in range(16)
        ]
        call_list += [
            {"success": True, "latency_ms": 100, "output_length": 2000}
            for _ in range(4)
        ]
        calls = {"Planner": call_list}
        hm = _make_health_monitor(calls)
        det = AnomalyDetector(output_length_multiplier=5.0, min_data_points=3)
        anomalies = det.scan_output_length_anomaly(hm)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == AnomalyType.OUTPUT_LENGTH_ANOMALY

    def test_no_output_length_field_skipped(self):
        """Calls without output_length field should be skipped."""
        calls = {"Planner": [{"success": True}] * 20}
        hm = _make_health_monitor(calls)
        det = AnomalyDetector(min_data_points=3)
        anomalies = det.scan_output_length_anomaly(hm)
        assert len(anomalies) == 0


# ── scan_all integration ───────────────────────────────────────

class TestScanAll:
    def test_scan_all_returns_combined(self):
        """scan_all should return anomalies from all detectors."""
        # Setup: token spike + repeated calls
        entries = [
            CostEntry("Planner", "gpt-4o", 1000, 500, 0.01, "s1", _ts(i))
            for i in range(20, 4, -1)
        ]
        entries += [
            CostEntry("Planner", "gpt-4o", 50000, 20000, 0.35, "s1", _ts(i))
            for i in range(4, 0, -1)
        ]
        ct = _make_cost_tracker(entries)

        calls = {
            "Planner": [{"success": True, "latency_ms": 100}] * 100,
        }
        hm = _make_health_monitor(calls)

        det = AnomalyDetector(
            token_spike_multiplier=10.0,
            repeated_calls_per_minute=50,
            min_data_points=3,
        )
        anomalies = det.scan_all(hm, ct)
        types = {a.anomaly_type for a in anomalies}
        assert AnomalyType.TOKEN_SPIKE in types
        assert AnomalyType.REPEATED_CALLS in types

    def test_scan_all_no_anomalies(self):
        """Clean system should return empty list."""
        ct = _make_cost_tracker([
            CostEntry("Planner", "gpt-4o", 1000, 500, 0.01, "s1", _ts(i))
            for i in range(20, 0, -1)
        ])
        calls = {"Planner": [{"success": True, "latency_ms": 100}] * 10}
        hm = _make_health_monitor(calls)

        det = AnomalyDetector(min_data_points=3)
        anomalies = det.scan_all(hm, ct)
        assert len(anomalies) == 0


# ── Singleton and convenience ──────────────────────────────────

class TestSingleton:
    def test_get_anomaly_detector_returns_singleton(self):
        d1 = get_anomaly_detector()
        d2 = get_anomaly_detector()
        assert d1 is d2

    def test_detect_anomalies_convenience(self):
        """detect_anomalies() should work with default singletons."""
        # Just verify it doesn't crash
        result = detect_anomalies()
        assert isinstance(result, list)


# ── Reset ──────────────────────────────────────────────────────

class TestReset:
    def test_reset_clears_history(self):
        det = AnomalyDetector()
        det._token_history["agent1"].append((1.0, 100))
        det._call_timestamps["agent1"].append(1.0)
        det.reset()
        assert len(det._token_history) == 0
        assert len(det._call_timestamps) == 0
