"""
Agent Discovery — AGP-powered 本机 Agent 扫描引擎

Primary: 扫描磁盘上的 .ahy-agent.json 文件（AGP 标准）
Fallback: 进程 + 端口扫描

支持 SSE 流式输出（扫到一个弹一个），最后汇总并提问是否注册。
"""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .agent_registry import (
    scan_filesystem,
    load_manifest,
    RuntimeRegistry,
    AgentManifest,
)


@dataclass
class DiscoveredAgent:
    agent_id: str = ""
    agent_name: str = ""
    framework: str = ""
    version: str = ""
    description: str = ""
    upstream_url: str = ""
    model: str = ""
    capabilities: dict = field(default_factory=dict)
    governance: dict = field(default_factory=dict)
    registry: dict = field(default_factory=dict)
    config_path: str | None = None
    status: str = "detected"
    pid: int | None = None
    port: int = 0
    source: str = "agp"

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "framework": self.framework,
            "version": self.version,
            "description": self.description,
            "upstream_url": self.upstream_url,
            "model": self.model,
            "capabilities": self.capabilities,
            "governance": self.governance,
            "registry": self.registry,
            "config_path": self.config_path,
            "status": self.status,
            "pid": self.pid,
            "port": self.port,
            "source": self.source,
        }

    @classmethod
    def from_manifest(cls, m: AgentManifest) -> DiscoveredAgent:
        return cls(
            agent_id=m.agent_id,
            agent_name=m.agent_name,
            framework=m.framework,
            version=m.version,
            description=m.description,
            upstream_url=m.upstream_url,
            model=m.model,
            capabilities=m.capabilities,
            governance=m.governance,
            registry=m.registry,
            config_path=m.config_path,
            status="detected",
            source="agp",
        )

    @classmethod
    def from_runtime(cls, state) -> DiscoveredAgent:
        return cls(
            agent_id=state.agent_id,
            agent_name=state.agent_name,
            framework=state.framework,
            version=state.version,
            upstream_url=state.upstream_url,
            model=state.model,
            status=state.status,
            pid=state.pid,
            port=state.port,
            source="runtime",
        )


# ── SSE Helpers ────────────────────────────────────────────────

def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── AGP File Scanning (Primary) ────────────────────────────────

def _scan_agp_files() -> list[DiscoveredAgent]:
    """Primary: find .ahy-agent.json files via AGP standard."""
    manifests = scan_filesystem()
    results = []
    for m in manifests:
        agent = DiscoveredAgent.from_manifest(m)
        # Check if running on declared port
        if m.upstream_url:
            port = _extract_port(m.upstream_url)
            agent.port = port
            probe = _probe_declared_agent(m.upstream_url)
            if probe:
                agent.status = "verified" if probe.get("verified") else "running"
                if probe.get("model") and probe["model"] != "unknown":
                    agent.model = probe["model"]
                agent.governance = {
                    **agent.governance,
                    "runtime_probe": probe,
                }
        results.append(agent)
    return results


# ── Runtime Registry ────────────────────────────────────────────

def _scan_runtime_registry() -> list[DiscoveredAgent]:
    """Secondary: check ~/.agent-registry/running/ for runtime state."""
    rt = RuntimeRegistry()
    running = rt.list_running()
    return [DiscoveredAgent.from_runtime(s) for s in running]


# ── Process Scanning (Fallback) ─────────────────────────────────

_AGENT_PROCESS_PATTERNS = [
    (r"(?:--mcp|mcp.?server|mcp.?client|\.mcp\.json)", "mcp"),
    (r"(?:agent\.py|engine\.py|langchain|langgraph|crewai|autogen)", "python"),
    (r"node.*(?:agent|claude-code|codex|gemini-cli|copilot)", "node"),
    (r"(?:OPENAI_API_KEY|ANTHROPIC_API_KEY|DEEPSEEK_API_KEY)", "llm-client"),
    (r"(?:ollama|lmstudio|llama\.cpp|vllm|text-generation-webui)", "model-server"),
]


def _scan_processes() -> list[DiscoveredAgent]:
    """Fallback: scan processes for agent-like patterns (no AGP config)."""
    return []  # Process scanning is best-effort; AGP config files are authoritative


# ── Port Scanning (Fallback) ───────────────────────────────────

def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _extract_port(url: str) -> int:
    if not url:
        return 0
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.port or 0
    except Exception:
        return 0


def _probe_agent_endpoint(port: int) -> dict | None:
    import urllib.request
    probes = [
        ("/v1/models", "openai"),
        ("/api/health", "ahy"),
        ("/health", "generic"),
        ("/api/agent/list", "governance"),
    ]
    for path, fw in probes:
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}{path}",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                body = resp.read().decode("utf-8", errors="replace")[:500]
                if path == "/v1/models" and "data" in body:
                    try:
                        data = json.loads(body)
                        models = data.get("data", [])
                        model_name = models[0].get("id", "unknown") if models else "unknown"
                    except Exception:
                        model_name = "openai-compatible"
                    return {"framework": fw, "model": model_name}
                if path == "/api/health" and ("status" in body or "ok" in body.lower()):
                    return {"framework": fw, "model": "detected"}
                if path == "/health" and resp.status == 200:
                    return {"framework": fw, "model": "detected"}
                if path == "/api/agent/list" and resp.status == 200:
                    return {"framework": fw, "model": "governance"}
        except Exception:
            continue
    return None


def _probe_declared_agent(upstream_url: str) -> dict | None:
    port = _extract_port(upstream_url)
    if not port or not _port_in_use(port):
        return None
    probe = _probe_url(upstream_url)
    if probe:
        return {"port": port, "verified": True, **probe}
    return {"port": port, "verified": False, "model": "unknown"}


def _probe_url(upstream_url: str) -> dict | None:
    import urllib.request
    upstream = upstream_url.rstrip("/")
    probes = [
        ("/health", "health"),
        ("/api/health", "api_health"),
        ("/v1/models", "openai_models"),
        ("/", "root"),
    ]
    for path, kind in probes:
        try:
            req = urllib.request.Request(
                f"{upstream}{path}",
                headers={"Accept": "application/json,text/plain,*/*"},
            )
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                body = resp.read().decode("utf-8", errors="replace")[:1000]
                model = "unknown"
                if kind == "openai_models":
                    try:
                        data = json.loads(body)
                        models = data.get("data", [])
                        if models:
                            model = models[0].get("id", "unknown")
                    except Exception:
                        model = "openai-compatible"
                return {
                    "probe_path": path,
                    "probe_kind": kind,
                    "http_status": resp.status,
                    "model": model,
                }
        except Exception:
            continue
    return None


def _scan_ports() -> list[DiscoveredAgent]:
    port_map = {
        11434: ("Ollama", "ollama"),
        5173: ("Dev Server", "dev-server"),
        8000: ("Local Service", "custom"),
        8001: ("Local Service", "custom"),
        8080: ("Local Service", "custom"),
        8699: ("Ahy Agent", "ahy"),
    }
    results = []
    for port, (name, fw) in port_map.items():
        if not _port_in_use(port):
            continue
        probe = _probe_agent_endpoint(port)
        if probe is None:
            continue
        results.append(DiscoveredAgent(
            agent_name=name, framework=probe.get("framework", fw),
            upstream_url=f"http://localhost:{port}",
            model=probe.get("model", "unknown"),
            status="running", port=port, source="port_scan",
        ))
    return results


# ── Agent Discovery Engine ─────────────────────────────────────

class AgentDiscovery:
    """Agent 发现引擎 — AGP-first scanning."""

    def scan_local(self) -> list[DiscoveredAgent]:
        results: list[DiscoveredAgent] = []

        # Primary: AGP files
        results.extend(_scan_agp_files())

        # Secondary: runtime registry
        results.extend(_scan_runtime_registry())

        # Port scan is an opt-in hint source, not AGP identity.
        if os.environ.get("AHY_AGP_PORT_SCAN", "").lower() in ("1", "true", "yes"):
            results.extend(_scan_ports())

        return self._deduplicate(results)

    def scan_local_stream(self) -> Iterator[str]:
        stages = [
            ("agp", _scan_agp_files),
            ("runtime", _scan_runtime_registry),
        ]
        if os.environ.get("AHY_AGP_PORT_SCAN", "").lower() in ("1", "true", "yes"):
            stages.append(("port", _scan_ports))
        all_found: list[DiscoveredAgent] = []
        for source, scan_fn in stages:
            try:
                batch = scan_fn()
                for agent in batch:
                    all_found.append(agent)
                    yield _sse_event("discovered", agent.to_dict())
            except Exception:
                pass

        yield _sse_event("summary", {
            "total": len(all_found),
            "agents": [a.to_dict() for a in all_found],
            "message": (
                f"Found {len(all_found)} agents on this machine. Register all?"
                if all_found else "No agents found. Register manually?"
            ),
        })

    @staticmethod
    def _deduplicate(agents: list[DiscoveredAgent]) -> list[DiscoveredAgent]:
        seen: dict[str, DiscoveredAgent] = {}
        for a in agents:
            key = a.agent_id or f"{a.agent_name}|{a.framework}"
            if key not in seen:
                seen[key] = a
            else:
                existing = seen[key]
                if a.status == "running" and existing.status != "running":
                    existing.status = "running"
                    existing.pid = a.pid
                    existing.port = a.port
                if a.config_path and not existing.config_path:
                    existing.config_path = a.config_path
                if a.model and a.model != "unknown" and existing.model == "unknown":
                    existing.model = a.model
                if a.source == "agp" and existing.source != "agp":
                    existing.source = "agp"
            if a.source == "agp":
                seen[key].source = "agp"
        return sorted(seen.values(), key=lambda a: (a.framework, a.agent_name))


# ── Module-level ───────────────────────────────────────────────

_discovery: AgentDiscovery | None = None


def get_discovery() -> AgentDiscovery:
    global _discovery
    if _discovery is None:
        _discovery = AgentDiscovery()
    return _discovery


def scan_local_agents() -> list[DiscoveredAgent]:
    return get_discovery().scan_local()
