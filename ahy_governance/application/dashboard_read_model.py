"""Read model for health dashboard API responses."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any


class DashboardReadModel:
    """Keeps health dashboard response shaping out of FastAPI route handlers."""

    def __init__(self, monitor: Any):
        self._monitor = monitor

    def dashboard(self) -> dict:
        return self._monitor.get_dashboard_data()

    def agents(self) -> list[dict]:
        agents = []
        for metrics in self._monitor.get_all_health().values():
            data = metrics.to_dict()
            agents.append({
                "agent_name": data["agent_name"],
                "status": data["status"],
                "success_rate": data["success_rate"],
                "latency_p95": data["latency_p95"],
                "error_rate": data["error_rate"],
                "last_heartbeat": data["last_heartbeat"],
                "total_calls": data["total_calls"],
                "calls_total": data["total_calls"],
            })
        return agents

    def agent(self, name: str):
        return self._monitor.get_agent_health(name)

    def unhealthy(self):
        return self._monitor.get_unhealthy_agents()

    def heartbeat(self, agent_name: str, status: str, latency_ms: float):
        return self._monitor.heartbeat(agent_name, status, latency_ms)

    def seed_demo(self) -> dict:
        """Seed demo health data using real monitor events."""
        agents = [
            ("Planner", "healthy", 25, 0, 35),
            ("Executor", "healthy", 20, 1, 55),
            ("Reviewer", "degraded", 20, 4, 280),
            ("Analyst", "healthy", 18, 0, 42),
            ("Governor", "offline", 5, 0, 20),
        ]

        for name, _, total_calls, errors, base_latency_ms in agents:
            self._monitor.heartbeat(name, "ok", base_latency_ms)
            for i in range(total_calls):
                is_error = i >= (total_calls - errors)
                latency_ms = base_latency_ms * (0.6 + 0.8 * random.random())
                if is_error:
                    latency_ms = 500 + 200 * random.random()
                elif name == "Reviewer":
                    latency_ms = 200 + 500 * random.random()
                self._monitor.record_call(name, success=not is_error, latency_ms=latency_ms)

        if "Governor" in self._monitor._heartbeats:
            old = datetime.now(timezone.utc) - timedelta(seconds=400)
            self._monitor._heartbeats["Governor"].timestamp = old.isoformat()

        return {"ok": True}
