"""
Health Monitor — Agent 健康仪表盘

特性:
  心跳监控 + 超时告警
  延迟百分位（P50/P95/P99）
  错误率 / 成功率 / 重试次数追踪
  Pipeline DAG 执行状态可视化
  综合 Dashboard 数据导出

用法:
  monitor = HealthMonitor()
  monitor.heartbeat("Planner", "ok", latency_ms=120)
  monitor.record_call("Planner", success=True, latency_ms=120)
  health = monitor.get_agent_health("Planner")
  dashboard = monitor.get_dashboard_data()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


# ── Enums ───────────────────────────────────────────────────────

class AgentStatus(Enum):
    HEALTHY = "healthy"          # success >= 95%, p95 < 60s, heartbeat < 30s
    DEGRADED = "degraded"        # success >= 80%, p95 < 300s, heartbeat < 120s
    UNHEALTHY = "unhealthy"      # below degraded thresholds
    OFFLINE = "offline"           # no heartbeat for 300s+


# ── Data classes ────────────────────────────────────────────────

@dataclass
class Heartbeat:
    agent_name: str
    status: str           # "ok", "timeout", "error"
    latency_ms: float
    timestamp: str


@dataclass
class AgentMetrics:
    agent_name: str
    success_count: int = 0
    error_count: int = 0
    retry_count: int = 0
    total_calls: int = 0
    latencies: list[float] = field(default_factory=list)
    last_heartbeat: str = ""
    status: AgentStatus = AgentStatus.OFFLINE

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return round(self.success_count / self.total_calls, 4)

    @property
    def error_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return round(self.error_count / self.total_calls, 4)

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "status": self.status.value,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "retry_count": self.retry_count,
            "total_calls": self.total_calls,
            "success_rate": self.success_rate,
            "error_rate": self.error_rate,
            "latency_p50": _percentile(self.latencies, 50) if self.latencies else 0,
            "latency_p95": _percentile(self.latencies, 95) if self.latencies else 0,
            "latency_p99": _percentile(self.latencies, 99) if self.latencies else 0,
            "last_heartbeat": self.last_heartbeat,
        }


@dataclass
class StepTiming:
    step_id: str
    agent_name: str
    status: str = "pending"   # pending, running, done, error
    duration_ms: float = 0
    start_time: str = ""
    end_time: str = ""


@dataclass
class PipelineRun:
    pipeline_id: str
    steps: dict[str, StepTiming] = field(default_factory=dict)
    status: str = "running"    # running, success, failed, blocked
    start_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    end_time: str = ""


# ── Helpers ─────────────────────────────────────────────────────

def _percentile(sorted_values: list[float], pct: int) -> float:
    if not sorted_values:
        return 0
    import math
    idx = max(0, int(math.ceil(len(sorted_values) * pct / 100)) - 1)
    return sorted_values[idx]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Default thresholds for status derivation (seconds)
OFFLINE_THRESHOLD = 300
UNHEALTHY_HEARTBEAT = 120
DEGRADED_HEARTBEAT = 30
UNHEALTHY_ERROR_RATE = 0.50
DEGRADED_ERROR_RATE = 0.05
UNHEALTHY_P95_LATENCY = 300.0
DEGRADED_P95_LATENCY = 60.0


# ── HealthMonitor ───────────────────────────────────────────────

class HealthMonitor:
    def __init__(self):
        self._heartbeats: dict[str, Heartbeat] = {}
        self._calls: dict[str, list[dict]] = {}
        self._pipeline_runs: dict[str, PipelineRun] = {}
        self._db = None  # set by server startup via set_database()

    def set_database(self, db):
        self._db = db

    # ── Heartbeat ─────────────────────────────────────────────

    def heartbeat(self, agent_name: str, status: str, latency_ms: float,
                  workspace_id: str = "") -> Heartbeat:
        hb = Heartbeat(
            agent_name=agent_name, status=status,
            latency_ms=latency_ms, timestamp=_utc_now(),
        )
        self._heartbeats[agent_name] = hb
        if self._db and self._db.enabled:
            self._db.heartbeat_upsert(agent_name, status, latency_ms,
                                      hb.timestamp, workspace_id)
        return hb

    # ── Record Call ───────────────────────────────────────────

    def record_call(
        self, agent_name: str, success: bool, latency_ms: float,
        session_id: str = "", workspace_id: str = "",
    ):
        if agent_name not in self._calls:
            self._calls[agent_name] = []
        self._calls[agent_name].append({
            "success": success,
            "latency_ms": latency_ms,
            "session_id": session_id,
        })
        if self._db and self._db.enabled:
            self._db.call_insert(agent_name, success, latency_ms,
                                 session_id, _utc_now(), workspace_id)

    # ── Agent Health ──────────────────────────────────────────

    def get_agent_health(self, agent_name: str) -> AgentMetrics | None:
        calls = self._calls.get(agent_name, [])
        hb = self._heartbeats.get(agent_name)

        # Fallback to DB if no in-memory data
        if not calls and not hb:
            if self._db and self._db.enabled:
                db_hb = self._db.heartbeat_get(agent_name)
                if db_hb:
                    hb = Heartbeat(
                        agent_name=agent_name,
                        status=db_hb.get("status", "unknown"),
                        latency_ms=db_hb.get("latency_ms", 0),
                        timestamp=db_hb.get("timestamp", ""),
                    )
                    self._heartbeats[agent_name] = hb  # hydrate memory
            if not calls and not hb:
                return None

        success = sum(1 for c in calls if c["success"])
        errors = sum(1 for c in calls if not c["success"])
        retries = errors  # each error is a potential retry
        latencies = sorted([c["latency_ms"] for c in calls])

        metrics = AgentMetrics(
            agent_name=agent_name,
            success_count=success,
            error_count=errors,
            retry_count=retries,
            total_calls=len(calls),
            latencies=latencies,
            last_heartbeat=hb.timestamp if hb else "",
        )
        metrics.status = self._derive_status(metrics)
        return metrics

    def get_all_health(self, workspace_id: str = "") -> dict[str, AgentMetrics]:
        agents = set(self._heartbeats.keys()) | set(self._calls.keys())
        # Merge agents from DB
        if self._db and self._db.enabled:
            for row in self._db.heartbeat_all(workspace_id):
                agents.add(row["agent_name"])
        result = {}
        for name in agents:
            m = self.get_agent_health(name)
            if m:
                result[name] = m
        return result

    def _derive_status(self, metrics: AgentMetrics) -> AgentStatus:
        now = datetime.now(timezone.utc)
        hb_age = float("inf")

        if metrics.last_heartbeat:
            try:
                hb_dt = datetime.fromisoformat(metrics.last_heartbeat)
                hb_age = (now - hb_dt).total_seconds()
            except (ValueError, TypeError):
                pass

        if hb_age > OFFLINE_THRESHOLD:
            return AgentStatus.OFFLINE

        p95 = _percentile(metrics.latencies, 95) if metrics.latencies else 0
        err = metrics.error_rate

        if (
            err > UNHEALTHY_ERROR_RATE
            or p95 > UNHEALTHY_P95_LATENCY
            or hb_age > UNHEALTHY_HEARTBEAT
        ):
            return AgentStatus.UNHEALTHY

        if (
            err > DEGRADED_ERROR_RATE
            or p95 > DEGRADED_P95_LATENCY
            or hb_age > DEGRADED_HEARTBEAT
        ):
            return AgentStatus.DEGRADED

        return AgentStatus.HEALTHY

    # ── Latency Percentiles ───────────────────────────────────

    def get_latency_percentiles(self, agent_name: str) -> dict:
        calls = self._calls.get(agent_name, [])
        latencies = sorted([c["latency_ms"] for c in calls])
        return {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "p99": _percentile(latencies, 99),
        }

    # ── Rates ─────────────────────────────────────────────────

    def get_success_rate(self, agent_name: str) -> float:
        m = self.get_agent_health(agent_name)
        return m.success_rate if m else 1.0

    def get_error_rate(self, agent_name: str) -> float:
        m = self.get_agent_health(agent_name)
        return m.error_rate if m else 0.0

    # ── Timeout Detection ─────────────────────────────────────

    def check_timeout(self, agent_name: str, max_age_seconds: float = 60) -> bool:
        hb = self._heartbeats.get(agent_name)
        if hb is None:
            return True
        try:
            hb_dt = datetime.fromisoformat(hb.timestamp)
            age = (datetime.now(timezone.utc) - hb_dt).total_seconds()
            return age > max_age_seconds
        except (ValueError, TypeError):
            return True

    # ── Unhealthy Agents ──────────────────────────────────────

    def get_unhealthy_agents(self, workspace_id: str = "") -> list[AgentMetrics]:
        all_h = self.get_all_health(workspace_id)
        return [
            m for m in all_h.values()
            if m.status in (AgentStatus.UNHEALTHY, AgentStatus.OFFLINE)
        ]

    def auto_heal_check(self, workspace_id: str = "") -> list[dict]:
        """Scan for unhealthy/offline agents and trigger self-healing.

        Returns list of HealResult dicts, one per agent that was checked.
        """
        from .self_healer import get_healer, IncidentType

        unhealthy = self.get_unhealthy_agents(workspace_id)
        results = []
        for m in unhealthy:
            md = m.to_dict()
            incident = "timeout" if md.get("latency_p95", 0) > 300 else "execution_error"
            try:
                it = IncidentType(incident)
            except ValueError:
                it = IncidentType.UNKNOWN

            heal_result = get_healer().self_heal(
                m.agent_name, it,
                f"Agent {m.agent_name} is {md.get('status', 'unhealthy')} "
                f"(success_rate={md.get('success_rate', 0):.1%}, p95={md.get('latency_p95', 0):.0f}ms)",
                context={"metrics": md},
                workspace_id=workspace_id,
            )
            results.append(heal_result.to_dict())
        return results

    # ── Agent Registry ────────────────────────────────────────

    def agent_register(self, agent_id: str, workspace_id: str, agent_name: str,
                        model: str, upstream_url: str, created_at: str) -> None:
        if self._db and self._db.enabled:
            self._db.agent_register(agent_id, workspace_id, agent_name,
                                     model, upstream_url, created_at)
        # Also seed in-memory heartbeat so agent appears in health views immediately
        self._heartbeats.setdefault(agent_name, Heartbeat(
            agent_name=agent_name, status="ok", latency_ms=0,
            timestamp=created_at,
        ))

    def agent_list(self, workspace_id: str = "") -> list[dict]:
        if self._db and self._db.enabled:
            return self._db.agent_list(workspace_id)
        return []

    def agent_get(self, agent_id: str) -> dict | None:
        if self._db and self._db.enabled:
            return self._db.agent_get(agent_id)
        return None

    def agent_delete(self, agent_id: str) -> bool:
        if self._db and self._db.enabled:
            return self._db.agent_delete(agent_id)
        return False

    # ── DB-backed queries ─────────────────────────────────────

    def calls_error_count(self, agent_name: str, workspace_id: str = "") -> int:
        if self._db and self._db.enabled:
            return self._db.calls_error_count(agent_name, workspace_id)
        return 0

    def calls_count_by_agent(self, agent_name: str, workspace_id: str = "") -> int:
        if self._db and self._db.enabled:
            return self._db.calls_count_by_agent(agent_name, workspace_id)
        return 0

    def calls_success_count(self, agent_name: str, workspace_id: str = "") -> int:
        if self._db and self._db.enabled:
            return self._db.calls_success_count(agent_name, workspace_id)
        return 0

    def calls_latencies(self, agent_name: str, limit: int = 500,
                        workspace_id: str = "") -> list[float]:
        if self._db and self._db.enabled:
            return self._db.calls_latencies(agent_name, limit, workspace_id)
        return []

    # ── Pipeline DAG ──────────────────────────────────────────

    def track_pipeline(self, pipeline_id: str, dag: dict) -> PipelineRun:
        steps = {}
        for step in dag.get("steps", []):
            sid = step["id"]
            steps[sid] = StepTiming(
                step_id=sid, agent_name=step.get("agent", ""),
                start_time=_utc_now(),
            )
        run = PipelineRun(pipeline_id=pipeline_id, steps=steps)
        self._pipeline_runs[pipeline_id] = run
        return run

    def update_step(
        self, pipeline_id: str, step_id: str,
        status: str, duration_ms: float,
    ):
        run = self._pipeline_runs.get(pipeline_id)
        if run and step_id in run.steps:
            s = run.steps[step_id]
            s.status = status
            s.duration_ms = duration_ms
            s.end_time = _utc_now()

    def complete_pipeline(self, pipeline_id: str, status: str):
        run = self._pipeline_runs.get(pipeline_id)
        if run:
            run.status = status
            run.end_time = _utc_now()

    def get_dag_status(self, pipeline_id: str) -> dict | None:
        run = self._pipeline_runs.get(pipeline_id)
        if run is None:
            return None
        return {
            "pipeline_id": run.pipeline_id,
            "status": run.status,
            "start_time": run.start_time,
            "end_time": run.end_time,
            "steps": [
                {
                    "step_id": s.step_id,
                    "agent": s.agent_name,
                    "status": s.status,
                    "duration_ms": s.duration_ms,
                }
                for s in run.steps.values()
            ],
        }

    # ── Dashboard ─────────────────────────────────────────────

    def get_dashboard_data(self, workspace_id: str = "") -> dict:
        agents_data = []
        all_h = self.get_all_health()
        healthy = 0
        unhealthy = 0
        total_calls = 0

        for m in all_h.values():
            d = m.to_dict()
            agents_data.append(d)
            if m.status == AgentStatus.HEALTHY:
                healthy += 1
            elif m.status in (AgentStatus.UNHEALTHY, AgentStatus.OFFLINE):
                unhealthy += 1
            total_calls += m.total_calls

        # Overall status
        if unhealthy > 0:
            overall = "unhealthy"
        elif healthy < len(all_h):
            overall = "degraded"
        elif len(all_h) == 0:
            overall = "unknown"
        else:
            overall = "healthy"

        return {
            "overall_status": overall,
            "timestamp": _utc_now(),
            "summary": {
                "total_agents": len(all_h),
                "healthy_count": healthy,
                "degraded_count": len(all_h) - healthy - unhealthy,
                "unhealthy_count": unhealthy,
                "total_calls": total_calls,
            },
            "agents": agents_data,
            "pipelines": [
                self.get_dag_status(pid) for pid in self._pipeline_runs
            ],
        }

    # ── Admin ─────────────────────────────────────────────────

    def reset(self):
        self._heartbeats.clear()
        self._calls.clear()
        self._pipeline_runs.clear()


# ── Module-level convenience ────────────────────────────────────

_monitor: HealthMonitor | None = None


def get_monitor() -> HealthMonitor:
    global _monitor
    if _monitor is None:
        _monitor = HealthMonitor()
    return _monitor


def check_health(agent_name: str) -> AgentMetrics | None:
    return get_monitor().get_agent_health(agent_name)
