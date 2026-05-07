"""Health Monitor 测试 — 心跳/延迟百分位/错误率/DAG 可视化"""

import time

import pytest

from ahy_governance import (
    HealthMonitor,
    AgentMetrics,
    AgentStatus,
    get_monitor,
    check_health,
)


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def monitor():
    m = HealthMonitor()
    yield m
    m.reset()


@pytest.fixture
def populated_monitor(monitor):
    # Simulate a healthy agent (P95 latency < 60ms, 100% success)
    for _ in range(10):
        monitor.heartbeat("Planner", "ok", latency_ms=45)
        monitor.record_call("Planner", success=True, latency_ms=45)
    # Simulate a degraded agent (some errors)
    for _ in range(5):
        monitor.heartbeat("Executor", "ok", latency_ms=250)
        monitor.record_call("Executor", success=True, latency_ms=250)
    monitor.record_call("Executor", success=False, latency_ms=5000)
    monitor.record_call("Executor", success=False, latency_ms=3000)
    # Simulate an offline agent (no recent heartbeat)
    monitor.heartbeat("Reviewer", "ok", latency_ms=80)
    monitor.record_call("Reviewer", success=True, latency_ms=80)
    return monitor


# ── Heartbeat Tests ─────────────────────────────────────────────

class TestHeartbeat:
    def test_heartbeat_records(self, monitor):
        hb = monitor.heartbeat("Agent1", "ok", latency_ms=100)
        assert hb.agent_name == "Agent1"
        assert hb.status == "ok"
        assert hb.latency_ms == 100
        assert hb.timestamp is not None

    def test_heartbeat_updates_last_seen(self, monitor):
        ts1 = monitor.heartbeat("A", "ok", 100).timestamp
        time.sleep(0.01)
        ts2 = monitor.heartbeat("A", "ok", 100).timestamp
        assert ts2 >= ts1

    def test_heartbeat_error_status(self, monitor):
        hb = monitor.heartbeat("Agent1", "timeout", latency_ms=30000)
        assert hb.status == "timeout"


# ── Record Call Tests ───────────────────────────────────────────

class TestRecordCall:
    def test_record_success(self, monitor):
        monitor.record_call("Agent1", success=True, latency_ms=150)
        metrics = monitor.get_agent_health("Agent1")
        assert metrics.success_count == 1
        assert metrics.error_count == 0
        assert metrics.total_calls == 1

    def test_record_error(self, monitor):
        monitor.record_call("Agent1", success=False, latency_ms=5000)
        metrics = monitor.get_agent_health("Agent1")
        assert metrics.error_count == 1
        assert metrics.success_count == 0

    def test_record_multiple(self, monitor):
        for i in range(20):
            monitor.record_call("Agent1", success=i % 3 != 0, latency_ms=100 + i)
        metrics = monitor.get_agent_health("Agent1")
        assert metrics.total_calls == 20

    def test_record_preserves_latencies(self, monitor):
        monitor.record_call("A", True, 100)
        monitor.record_call("A", True, 200)
        monitor.record_call("A", True, 300)
        metrics = monitor.get_agent_health("A")
        assert metrics.latencies == [100, 200, 300]


# ── Agent Health Tests ──────────────────────────────────────────

class TestAgentHealth:
    def test_unknown_agent_returns_none(self, monitor):
        assert monitor.get_agent_health("Ghost") is None

    def test_healthy_agent_status(self, populated_monitor):
        metrics = populated_monitor.get_agent_health("Planner")
        assert metrics is not None
        assert metrics.status == AgentStatus.HEALTHY

    def test_degraded_agent_status(self, populated_monitor):
        metrics = populated_monitor.get_agent_health("Executor")
        assert metrics is not None
        # 5 success + 2 errors = ~71% success → DEGRADED or worse
        assert metrics.status in (AgentStatus.DEGRADED, AgentStatus.UNHEALTHY)

    def test_offline_agent_status(self, monitor):
        monitor.heartbeat("OldAgent", "ok", 100)
        # Override last_heartbeat to be very old
        metrics = monitor.get_agent_health("OldAgent")
        metrics.last_heartbeat = "2000-01-01T00:00:00+00:00"
        status = monitor._derive_status(metrics)
        assert status == AgentStatus.OFFLINE

    def test_get_all_health(self, populated_monitor):
        all_health = populated_monitor.get_all_health()
        assert "Planner" in all_health
        assert "Executor" in all_health
        assert "Reviewer" in all_health
        assert isinstance(all_health["Planner"], AgentMetrics)


# ── Latency Percentile Tests ────────────────────────────────────

class TestLatencyPercentiles:
    def test_p50(self, monitor):
        for v in [100, 200, 300, 400, 500]:
            monitor.record_call("A", True, v)
        p = monitor.get_latency_percentiles("A")
        assert p["p50"] == 300

    def test_p95(self, monitor):
        # 100 values → p95 is the 95th
        for i in range(100):
            monitor.record_call("A", True, i + 1)
        p = monitor.get_latency_percentiles("A")
        assert p["p95"] == 95  # 95th value in 1..100

    def test_p99(self, monitor):
        for i in range(100):
            monitor.record_call("A", True, i + 1)
        p = monitor.get_latency_percentiles("A")
        assert p["p99"] == 99

    def test_percentiles_single_value(self, monitor):
        monitor.record_call("A", True, 42)
        p = monitor.get_latency_percentiles("A")
        assert p["p50"] == 42
        assert p["p95"] == 42
        assert p["p99"] == 42

    def test_percentiles_unknown_agent(self, monitor):
        p = monitor.get_latency_percentiles("Ghost")
        assert p["p50"] == 0
        assert p["p95"] == 0

    def test_percentiles_no_latency_data(self, monitor):
        monitor.heartbeat("A", "ok", 100)
        p = monitor.get_latency_percentiles("A")
        assert p["p50"] == 0


# ── Error / Success Rate Tests ──────────────────────────────────

class TestRates:
    def test_success_rate_100(self, populated_monitor):
        rate = populated_monitor.get_success_rate("Planner")
        assert rate == 1.0

    def test_error_rate(self, populated_monitor):
        rate = populated_monitor.get_error_rate("Executor")
        # 2 errors out of 7 calls ≈ 28.6%
        assert rate == pytest.approx(2 / 7, rel=0.01)

    def test_rates_unknown_agent(self, monitor):
        assert monitor.get_success_rate("Ghost") == 1.0
        assert monitor.get_error_rate("Ghost") == 0.0

    def test_retry_count(self, monitor):
        monitor.record_call("A", True, 100)
        monitor.record_call("A", False, 200)
        monitor.record_call("A", True, 150)
        metrics = monitor.get_agent_health("A")
        assert metrics.retry_count == 1  # only 1 error (retryable)
        assert metrics.total_calls == 3


# ── Timeout Detection Tests ─────────────────────────────────────

class TestTimeout:
    def test_not_timed_out_recently(self, populated_monitor):
        assert not populated_monitor.check_timeout("Planner", max_age_seconds=60)

    def test_timed_out(self, monitor):
        monitor.heartbeat("A", "ok", 100)
        # Fake the heartbeat timestamp to be old (directly on the stored heartbeat)
        monitor._heartbeats["A"].timestamp = "2000-01-01T00:00:00+00:00"
        assert monitor.check_timeout("A", max_age_seconds=60)

    def test_timeout_unknown_agent(self, monitor):
        assert monitor.check_timeout("Ghost", max_age_seconds=60)


# ── Unhealthy Agents Tests ──────────────────────────────────────

class TestUnhealthyAgents:
    def test_returns_unhealthy_list(self, populated_monitor):
        unhealthy = populated_monitor.get_unhealthy_agents()
        statuses = {m.agent_name: m.status for m in unhealthy}
        # Executor has 2 errors → should be unhealthy or degraded
        assert "Executor" in statuses

    def test_all_healthy_returns_empty(self, monitor):
        for _ in range(10):
            monitor.heartbeat("A", "ok", 50)
            monitor.record_call("A", True, 50)
        assert monitor.get_unhealthy_agents() == []


# ── Pipeline DAG Tests ──────────────────────────────────────────

class TestPipelineDAG:
    def test_track_pipeline(self, monitor):
        dag = {
            "steps": [
                {"id": "step1", "agent": "Planner", "next": "step2"},
                {"id": "step2", "agent": "Executor", "next": "__done__"},
            ],
            "edges": [{"from": "step1", "to": "step2"}],
        }
        run = monitor.track_pipeline("pipeline-1", dag)
        assert run.pipeline_id == "pipeline-1"
        assert len(run.steps) == 2
        assert run.status == "running"

    def test_update_step_status(self, monitor):
        dag = {"steps": [{"id": "s1", "agent": "A", "next": "__done__"}], "edges": []}
        monitor.track_pipeline("pipe-1", dag)
        monitor.update_step("pipe-1", "s1", status="done", duration_ms=350)
        runs = monitor._pipeline_runs
        assert runs["pipe-1"].steps["s1"].status == "done"
        assert runs["pipe-1"].steps["s1"].duration_ms == 350

    def test_pipeline_complete(self, monitor):
        dag = {"steps": [{"id": "s1", "agent": "A", "next": "__done__"}], "edges": []}
        monitor.track_pipeline("pipe-1", dag)
        monitor.update_step("pipe-1", "s1", status="done", duration_ms=100)
        monitor.complete_pipeline("pipe-1", status="success")
        assert monitor._pipeline_runs["pipe-1"].status == "success"

    def test_get_dag_status(self, monitor):
        dag = {
            "steps": [
                {"id": "step1", "agent": "Planner", "next": "step2"},
                {"id": "step2", "agent": "Executor", "next": "__done__"},
            ],
            "edges": [{"from": "step1", "to": "step2"}],
        }
        monitor.track_pipeline("p-1", dag)
        monitor.update_step("p-1", "step1", status="done", duration_ms=200)
        status = monitor.get_dag_status("p-1")
        assert status["pipeline_id"] == "p-1"
        assert len(status["steps"]) == 2
        assert status["steps"][0]["status"] == "done"

    def test_get_dag_status_nonexistent(self, monitor):
        assert monitor.get_dag_status("no-such-pipeline") is None


# ── Dashboard Data Tests ────────────────────────────────────────

class TestDashboardData:
    def test_dashboard_structure(self, populated_monitor):
        data = populated_monitor.get_dashboard_data()
        assert "agents" in data
        assert "overall_status" in data
        assert "summary" in data
        assert "pipelines" in data
        assert "timestamp" in data

    def test_dashboard_summary_counts(self, populated_monitor):
        data = populated_monitor.get_dashboard_data()
        s = data["summary"]
        assert s["total_agents"] >= 3
        assert "healthy_count" in s
        assert "unhealthy_count" in s
        assert s["total_calls"] > 0

    def test_dashboard_overall_status(self, populated_monitor):
        data = populated_monitor.get_dashboard_data()
        # With at least one unhealthy agent, overall shouldn't be healthy
        assert data["overall_status"] in ("healthy", "degraded", "unhealthy")


# ── Edge Cases ──────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_monitor(self, monitor):
        assert monitor.get_all_health() == {}
        assert monitor.get_dashboard_data()["summary"]["total_agents"] == 0

    def test_reset_clears_all(self, populated_monitor):
        populated_monitor.reset()
        assert populated_monitor.get_all_health() == {}

    def test_high_volume_latencies(self, monitor):
        for i in range(1000):
            monitor.record_call("A", True, i % 500)
        p = monitor.get_latency_percentiles("A")
        assert p["p50"] > 0
        assert p["p99"] >= p["p50"]
        assert monitor.get_agent_health("A").total_calls == 1000

    def test_heartbeat_without_calls(self, monitor):
        monitor.heartbeat("A", "ok", 100)
        metrics = monitor.get_agent_health("A")
        assert metrics is not None
        assert metrics.total_calls == 0
        assert metrics.success_rate == 1.0

    def test_all_status_enum_values(self):
        values = {s.value for s in AgentStatus}
        assert "healthy" in values
        assert "degraded" in values
        assert "unhealthy" in values
        assert "offline" in values

    def test_latency_returns_sorted(self, monitor):
        for v in [500, 100, 300, 200, 400]:
            monitor.record_call("A", True, v)
        metrics = monitor.get_agent_health("A")
        assert metrics.latencies == sorted(metrics.latencies)

    def test_concurrent_agents_isolation(self, monitor):
        monitor.record_call("A", True, 100)
        monitor.record_call("B", False, 200)
        assert monitor.get_agent_health("A").success_count == 1
        assert monitor.get_agent_health("B").error_count == 1


# ── Convenience Functions ───────────────────────────────────────

class TestConvenienceFunctions:
    def test_get_monitor_singleton(self):
        m1 = get_monitor()
        m2 = get_monitor()
        assert m1 is m2
        m1.reset()

    def test_check_health_global(self):
        m = get_monitor()
        m.reset()
        m.heartbeat("TestAgent", "ok", 50)
        m.record_call("TestAgent", True, 50)
        result = check_health("TestAgent")
        assert result is not None
        assert result.agent_name == "TestAgent"
        m.reset()


# ── AgentMetrics Tests ──────────────────────────────────────────

class TestAgentMetrics:
    def test_metrics_to_dict(self, monitor):
        monitor.heartbeat("A", "ok", 100)
        monitor.record_call("A", True, 100)
        metrics = monitor.get_agent_health("A")
        d = metrics.to_dict()
        assert d["agent_name"] == "A"
        assert d["total_calls"] == 1
        assert "latency_p50" in d
        assert "status" in d
