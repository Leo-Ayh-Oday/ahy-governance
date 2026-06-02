"""
Agent Discovery — 本机 Agent 扫描引擎

扫描配置文件 + 进程 + 端口，自动发现本地运行的所有 Agent。
支持 SSE 流式输出（扫到一个弹一个），最后汇总并提问是否注册。

用法:
  discovery = get_discovery()
  agents = discovery.scan_local()
  for agent in agents:
      print(f"Found: {agent.agent_name} ({agent.framework})")
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator


@dataclass
class DiscoveredAgent:
    agent_name: str
    framework: str
    upstream_url: str = ""
    model: str = ""
    status: str = "detected"
    pid: int | None = None
    config_path: str | None = None
    source: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "framework": self.framework,
            "upstream_url": self.upstream_url,
            "model": self.model,
            "status": self.status,
            "pid": self.pid,
            "config_path": self.config_path,
            "source": self.source,
        }


# ── SSE Helpers ────────────────────────────────────────────────

def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── Config File Scanning ───────────────────────────────────────

def _scan_ahy_agent_config() -> list[DiscoveredAgent]:
    """Scan ~/.agent/config/settings.json"""
    home = Path.home()
    config_path = home / ".agent" / "config" / "settings.json"
    if not config_path.exists():
        return []
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        model_cfg = cfg.get("model", {})
        web_cfg = cfg.get("channels", {}).get("web", {})
        port = web_cfg.get("port", 5173)
        return [DiscoveredAgent(
            agent_name="Ahy Agent",
            framework="ahy",
            upstream_url=f"http://localhost:{port}",
            model=model_cfg.get("model", "unknown"),
            status="running" if _port_in_use(port) else "detected",
            config_path=str(config_path),
            source="config_file",
        )]
    except Exception:
        return []


def _scan_claude_mcp_config() -> list[DiscoveredAgent]:
    """Scan ~/.claude/.mcp.json for MCP agents"""
    paths = [
        Path.home() / ".claude" / ".mcp.json",
        Path(os.getcwd()) / ".mcp.json",
    ]
    results = []
    for config_path in paths:
        if not config_path.exists():
            continue
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            servers = cfg.get("mcpServers", {})
            for name, srv in servers.items():
                cmd = srv.get("command", "")
                args = srv.get("args", [])
                results.append(DiscoveredAgent(
                    agent_name=name,
                    framework="mcp",
                    upstream_url=f"stdio://{cmd}",
                    model="mcp-server",
                    status="detected",
                    config_path=str(config_path),
                    source="config_file",
                ))
        except Exception:
            pass
    return results


def _scan_codex_config() -> list[DiscoveredAgent]:
    """Scan for Codex CLI"""
    paths = [
        Path.home() / ".codex" / "config.toml",
        Path.home() / ".codex" / "config.json",
        Path.home() / ".config" / "codex" / "config.toml",
    ]
    for p in paths:
        if p.exists():
            return [DiscoveredAgent(
                agent_name="Codex CLI",
                framework="codex",
                upstream_url="stdio://codex",
                model="gpt-5.3-codex",
                status="detected",
                config_path=str(p),
                source="config_file",
            )]
    return []


# ── Process Scanning ───────────────────────────────────────────

def _scan_processes() -> list[DiscoveredAgent]:
    """Scan running processes for known agent patterns"""
    results = []
    if sys.platform != "win32":
        return results  # Windows only for now via psutil

    try:
        import subprocess
        out = subprocess.run(
            ["wmic", "process", "get", "ProcessId,CommandLine", "/format:csv"],
            capture_output=True, text=True, timeout=10,
        )
        for line in out.stdout.splitlines():
            line_lower = line.lower()
            pid_str = line.split(",")[-1].strip() if "," in line else ""
            if not pid_str or not pid_str.isdigit():
                continue

            if "agent.py" in line_lower or "engine.py" in line_lower:
                results.append(DiscoveredAgent(
                    agent_name="Python Agent",
                    framework="python",
                    upstream_url="http://localhost:8000",
                    model="unknown",
                    status="running",
                    pid=int(pid_str),
                    source="process",
                ))
            elif "node" in line_lower and ("agent" in line_lower or "_start_web" in line_lower):
                results.append(DiscoveredAgent(
                    agent_name="Node Agent",
                    framework="node",
                    upstream_url="http://localhost:5173",
                    model="unknown",
                    status="running",
                    pid=int(pid_str),
                    source="process",
                ))
            elif "ollama" in line_lower:
                results.append(DiscoveredAgent(
                    agent_name="Ollama",
                    framework="ollama",
                    upstream_url="http://localhost:11434",
                    model="local",
                    status="running",
                    pid=int(pid_str),
                    source="process",
                ))
    except Exception:
        pass

    return results


# ── Port Scanning ──────────────────────────────────────────────

def _port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _scan_ports() -> list[DiscoveredAgent]:
    """Scan known agent ports"""
    port_map = {
        11434: ("Ollama", "ollama", "local"),
        5173: ("Vite Dev Server", "dev-server", "unknown"),
        8000: ("Local Agent", "custom", "unknown"),
        8001: ("Local Agent", "custom", "unknown"),
        8080: ("Local Agent", "custom", "unknown"),
    }
    results = []
    for port, (name, fw, model) in port_map.items():
        if _port_in_use(port):
            results.append(DiscoveredAgent(
                agent_name=name,
                framework=fw,
                upstream_url=f"http://localhost:{port}",
                model=model,
                status="running",
                source="port_scan",
            ))
    return results


# ── Agent Discovery Engine ─────────────────────────────────────

class AgentDiscovery:
    """Agent 发现引擎."""

    def scan_local(self) -> list[DiscoveredAgent]:
        results = []
        results.extend(_scan_ahy_agent_config())
        results.extend(_scan_claude_mcp_config())
        results.extend(_scan_codex_config())
        results.extend(_scan_processes())
        results.extend(_scan_ports())
        return self._deduplicate(results)

    def scan_local_stream(self) -> Iterator[str]:
        """SSE 流式扫描 — 扫到一个弹出一个."""
        scanners = [
            ("config_file", _scan_ahy_agent_config),
            ("config_file", _scan_claude_mcp_config),
            ("config_file", _scan_codex_config),
            ("process", _scan_processes),
            ("port", _scan_ports),
        ]
        all_found = []
        for source, scan_fn in scanners:
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
            "message": f"Found {len(all_found)} agents on this machine. Register all?" if all_found
                       else "No agents found. Register manually?",
        })

    @staticmethod
    def _deduplicate(agents: list[DiscoveredAgent]) -> list[DiscoveredAgent]:
        seen: dict[str, DiscoveredAgent] = {}
        for a in agents:
            key = f"{a.agent_name}|{a.framework}"
            if key not in seen:
                seen[key] = a
            else:
                # Merge: prefer "running" status and config_file source
                existing = seen[key]
                if a.status == "running" and existing.status != "running":
                    existing.status = "running"
                    existing.pid = a.pid
                if a.config_path and not existing.config_path:
                    existing.config_path = a.config_path
                if a.model and a.model != "unknown" and existing.model == "unknown":
                    existing.model = a.model
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
