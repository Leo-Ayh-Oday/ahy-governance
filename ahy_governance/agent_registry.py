"""
AGP 鈥?Agent Governance Protocol: Agent 鑷敞鍐屾爣鍑?
涓夊眰鏋舵瀯:
  1. .ahy-agent.json  (Agent 椤圭洰鏍圭洰褰?  鈫?寮€鍙戣€呮墜鍐欙紝"鎴戞槸涓€涓?Agent"
  2. ~/.agent-registry/running/          鈫?Agent 鍚姩鏃惰嚜鍔ㄥ啓 (port/pid/started_at)
  3. Governance DB (registered_agents)   鈫?娉ㄥ唽鍚庢寔涔呭寲

绫讳技 MCP 瀹氫箟宸ュ叿鏈嶅姟鍣ㄦ爣鍑嗭紝AGP 瀹氫箟 Agent 鑷敞鍐屾爣鍑嗐€?妗嗘灦鏃犲叧 鈥?CrewAI/AutoGen/LangGraph/鑷爺妗嗘灦 閮藉彲浠ラ伒瀹堛€?"""

from __future__ import annotations

import json
import os
import socket
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Canonical AGP schema for .ahy-agent.json.
_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "agp.schema.json"


def load_agp_schema() -> dict[str, Any]:
    """Load the canonical AGP manifest schema."""
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


AGP_SCHEMA = load_agp_schema()

KNOWN_FRAMEWORKS = {
    "ahy", "crewai", "autogen", "langgraph", "openai-agents",
    "claude-code", "codex", "gemini-cli", "custom", "mcp",
}


# 鈹€鈹€ Data Classes 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@dataclass
class AgentManifest:
    """Parsed .ahy-agent.json content."""
    agent_name: str
    framework: str
    version: str
    manifest_version: str = "1.0"
    agent_id: str = ""
    description: str = ""
    upstream_url: str = ""
    model: str = ""
    capabilities: dict = field(default_factory=dict)
    registry: dict = field(default_factory=dict)
    governance: dict = field(default_factory=dict)
    config_path: str | None = None  # where the file was found

    def __post_init__(self):
        """Stable ID derived from name+framework. Same agent 鈫?same ID."""
        if not self.agent_id:
            raw = f"{self.framework}:{self.agent_name}"
            self.agent_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, raw))

    @property
    def heartbeat_seconds(self) -> int:
        return self.registry.get("heartbeat_seconds", 30)

    @property
    def auto_register(self) -> bool:
        return self.registry.get("auto_register", False)

    @property
    def enabled(self) -> bool:
        return self.registry.get("enabled", True)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["agent_id"] = self.agent_id
        return d


@dataclass
class RuntimeState:
    """Runtime state written to ~/.agent-registry/running/{agent_id}.json"""
    agent_id: str
    agent_name: str
    framework: str
    version: str
    upstream_url: str
    model: str
    pid: int
    port: int
    started_at: str
    last_heartbeat: str
    status: str = "running"  # running | degraded | stopped

    def to_dict(self) -> dict:
        return asdict(self)


# 鈹€鈹€ Validation 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

class AGPValidationError(Exception):
    pass


def validate_manifest(data: dict) -> list[str]:
    """Validate .ahy-agent.json against AGP schema. Returns list of warnings."""
    _reject_inline_auth_secrets(data)
    try:
        import jsonschema
        jsonschema.validate(instance=data, schema=AGP_SCHEMA)
    except ImportError:
        _validate_manifest_without_jsonschema(data)
    except Exception as exc:
        raise AGPValidationError(str(exc)) from exc

    registry = data.get("registry", {})
    hb = registry.get("heartbeat_seconds", 30)
    if not isinstance(hb, int) or hb < 5 or hb > 3600:
        raise AGPValidationError(f"registry.heartbeat_seconds must be >= 5, got: {hb}")

    framework = data.get("framework", "")
    warnings = []
    if framework and framework not in KNOWN_FRAMEWORKS:
        warnings.append(
            f"Unknown framework '{framework}'. Known: {', '.join(sorted(KNOWN_FRAMEWORKS))}. "
            f"AGP is framework-agnostic so this is OK, but consider registering '{framework}' upstream."
        )

    return warnings


def _reject_inline_auth_secrets(data: dict) -> None:
    auth = data.get("auth", {})
    for secret_key in ("token", "api_key", "password", "secret"):
        if isinstance(auth, dict) and secret_key in auth:
            raise AGPValidationError(f"auth.{secret_key} must not be stored in AGP manifest")


def _validate_manifest_without_jsonschema(data: dict) -> None:
    for field in AGP_SCHEMA["required"]:
        if field not in data:
            raise AGPValidationError(f"Missing required field: '{field}'")
    if data.get("manifest_version") != "1.0":
        raise AGPValidationError("manifest_version must be '1.0'")
    for field in ("agent_name", "framework", "version", "upstream_url", "model"):
        if not isinstance(data.get(field), str) or not data[field]:
            raise AGPValidationError(f"{field} must be a non-empty string")
    if not data["upstream_url"].startswith(("http://", "https://", "stdio://")):
        raise AGPValidationError("upstream_url must start with http://, https://, or stdio://")
    capabilities = data.get("capabilities")
    if not isinstance(capabilities, dict):
        raise AGPValidationError("capabilities must be an object")
    for field in ("can_read", "can_search", "can_write_local"):
        if not isinstance(capabilities.get(field), bool):
            raise AGPValidationError(f"capabilities.{field} must be boolean")
    registry = data.get("registry")
    if not isinstance(registry, dict):
        raise AGPValidationError("registry must be an object")
    if not isinstance(registry.get("enabled"), bool):
        raise AGPValidationError("registry.enabled must be boolean")


def load_manifest(path: str | Path) -> AgentManifest:
    """Load and validate a .ahy-agent.json file."""
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    warnings = validate_manifest(raw)
    if warnings:
        import logging
        log = logging.getLogger("agp")
        for w in warnings:
            log.warning(w)

    capabilities = dict(raw.get("capabilities", {}))
    defaults = _capability_defaults()
    for k, v in defaults.items():
        capabilities.setdefault(k, v)

    registry = dict(raw.get("registry", {}))
    registry.setdefault("enabled", True)
    registry.setdefault("heartbeat_seconds", 30)
    registry.setdefault("auto_register", False)

    governance = dict(raw.get("governance", raw.get("metadata", {})))
    governance.setdefault("require_approval", False)
    governance.setdefault("tags", [])

    return AgentManifest(
        manifest_version=raw.get("manifest_version", "1.0"),
        agent_id=raw.get("agent_id", ""),
        agent_name=raw["agent_name"],
        framework=raw["framework"],
        version=raw["version"],
        description=raw.get("description", ""),
        upstream_url=raw.get("upstream_url", ""),
        model=raw.get("model", ""),
        capabilities=capabilities,
        registry=registry,
        governance=governance,
        config_path=str(path.resolve()),
    )


def _capability_defaults() -> dict:
    cap_schema = AGP_SCHEMA["properties"]["capabilities"]["properties"]
    return {k: v["default"] for k, v in cap_schema.items() if "default" in v}


# 鈹€鈹€ Disk Scanner 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def scan_filesystem(search_roots: list[str | Path] | None = None) -> list[AgentManifest]:
    """Find all .ahy-agent.json files on disk.

    search_roots: list of directories to scan recursively.
                  Defaults to [cwd, ~/projects, ~/dev, ~/src].
    """
    if search_roots is None:
        search_roots = _default_search_roots()

    found: dict[str, AgentManifest] = {}  # agent_id 鈫?manifest
    seen_paths: set[str] = set()

    for root in search_roots:
        root = Path(root).expanduser().resolve()
        if not root.is_dir():
            continue
        for filepath in _walk_for_agp_files(root):
            resolved = str(filepath.resolve())
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            try:
                manifest = load_manifest(filepath)
                if manifest.enabled:
                    # First found wins; later duplicates ignored
                    found.setdefault(manifest.agent_id, manifest)
            except Exception:
                continue

    return sorted(found.values(), key=lambda m: (m.framework, m.agent_name))


def _default_search_roots() -> list[Path]:
    candidates = [Path.cwd()]
    env_roots = os.environ.get("AHY_AGP_SEARCH_ROOTS", "")
    for raw in env_roots.split(os.pathsep):
        if raw.strip():
            candidates.append(Path(raw.strip()).expanduser())
    candidates.extend(_known_search_roots())

    roots: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        try:
            resolved = path.expanduser().resolve()
        except Exception:
            continue
        if resolved.is_dir() and str(resolved) not in seen:
            roots.append(resolved)
            seen.add(str(resolved))
    return roots or [Path.cwd()]


def _known_search_roots() -> list[Path]:
    config_path = Path.home() / ".agent-registry" / "known-roots.json"
    if not config_path.is_file():
        return []
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    roots = data.get("roots", data if isinstance(data, list) else [])
    return [Path(p).expanduser() for p in roots if isinstance(p, str) and p.strip()]


def _walk_for_agp_files(root: Path) -> list[Path]:
    """Walk directory tree looking for .ahy-agent.json files.
    Stops recursing into node_modules, .git, __pycache__, venv, .venv."""
    results = []
    skip_dirs = {"node_modules", ".git", "__pycache__", "venv", ".venv",
                 ".tox", "dist", "build", ".next", "target"}

    # Check root itself first
    candidate = root / ".ahy-agent.json"
    if candidate.is_file():
        results.append(candidate)
        return results  # Don't recurse if root has its own manifest

    try:
        for entry in root.iterdir():
            if entry.name in skip_dirs or entry.name.startswith("."):
                continue
            if entry.is_dir():
                results.extend(_walk_for_agp_files(entry))
    except PermissionError:
        pass
    return results


# 鈹€鈹€ Runtime Registry (~/.agent-registry/running/) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

class RuntimeRegistry:
    """Manage ~/.agent-registry/running/ 鈥?per-agent runtime state.

    Agent writes at startup:
        RuntimeRegistry().write_state(agent_id, pid, port, ...)

    Governance reads to discover running agents:
        RuntimeRegistry().list_running()
    """

    def __init__(self, base_dir: str | Path | None = None):
        if base_dir is None:
            base_dir = Path.home() / ".agent-registry"
        self._base = Path(base_dir)
        self._running_dir = self._base / "running"
        self._running_dir.mkdir(parents=True, exist_ok=True)

    @property
    def running_dir(self) -> Path:
        return self._running_dir

    def state_path(self, agent_id: str) -> Path:
        return self._running_dir / f"{agent_id}.json"

    def write_state(self, agent_id: str, agent_name: str, framework: str,
                    version: str, upstream_url: str, model: str,
                    pid: int | None = None, port: int | None = None) -> RuntimeState:
        now = datetime.now(timezone.utc).isoformat()
        if pid is None:
            pid = os.getpid()
        if port is None:
            port = _extract_port(upstream_url)

        state = RuntimeState(
            agent_id=agent_id, agent_name=agent_name, framework=framework,
            version=version, upstream_url=upstream_url, model=model,
            pid=pid, port=port, started_at=now, last_heartbeat=now, status="running",
        )
        self.state_path(agent_id).write_text(
            json.dumps(state.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return state

    def read_state(self, agent_id: str) -> RuntimeState | None:
        p = self.state_path(agent_id)
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return RuntimeState(**data)

    def heartbeat(self, agent_id: str) -> bool:
        """Update last_heartbeat timestamp. Returns False if state file missing."""
        state = self.read_state(agent_id)
        if state is None:
            return False
        state.last_heartbeat = datetime.now(timezone.utc).isoformat()
        self.state_path(agent_id).write_text(
            json.dumps(state.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return True

    def remove_state(self, agent_id: str):
        p = self.state_path(agent_id)
        if p.exists():
            p.unlink()

    def list_running(self) -> list[RuntimeState]:
        results = []
        for f in sorted(self._running_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                results.append(RuntimeState(**data))
            except Exception:
                pass
        return results

    def scan_stale(self, max_heartbeat_age_seconds: int = 120) -> list[RuntimeState]:
        """Return agents whose heartbeat is older than threshold."""
        now = datetime.now(timezone.utc)
        stale = []
        for state in self.list_running():
            try:
                last = datetime.fromisoformat(state.last_heartbeat)
                if (now - last).total_seconds() > max_heartbeat_age_seconds:
                    stale.append(state)
            except Exception:
                stale.append(state)
        return stale


def _extract_port(url: str) -> int:
    """Extract port from http://host:port or return 0."""
    if not url:
        return 0
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.port or 0
    except Exception:
        return 0


# 鈹€鈹€ Registration Orchestrator 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

class AgentRegistrar:
    """Orchestrates the full AGP registration flow.

    1. scan_filesystem()  鈫?find .ahy-agent.json files
    2. list_running()      鈫?check runtime registry
    3. register(manifest)  鈫?persist to governance DB
    """

    def __init__(self, db=None):
        self._db = db
        self.runtime = RuntimeRegistry()

    def set_database(self, db):
        self._db = db

    def discover(self) -> list[dict]:
        """Full discovery: merge config files + runtime states."""
        manifests = scan_filesystem()
        running = {s.agent_id: s for s in self.runtime.list_running()}

        results = []
        for m in manifests:
            rt = running.get(m.agent_id)
            results.append({
                "agent_id": m.agent_id,
                "agent_name": m.agent_name,
                "framework": m.framework,
                "version": m.version,
                "description": m.description,
                "upstream_url": m.upstream_url,
                "model": m.model,
                "capabilities": m.capabilities,
                "governance": m.governance,
                "registry": m.registry,
                "config_path": m.config_path,
                "runtime": rt.to_dict() if rt else None,
                "status": rt.status if rt else "detected",
                "registered": self._is_registered(m.agent_id) if self._db else False,
            })

        # Also include runtime-only agents (no config file found but running)
        for rt_state in running.values():
            if rt_state.agent_id not in {m.agent_id for m in manifests}:
                results.append({
                    "agent_id": rt_state.agent_id,
                    "agent_name": rt_state.agent_name,
                    "framework": rt_state.framework,
                    "version": rt_state.version,
                    "description": "",
                    "upstream_url": rt_state.upstream_url,
                    "model": rt_state.model,
                    "capabilities": {},
                    "governance": {},
                    "registry": {},
                    "config_path": None,
                    "runtime": rt_state.to_dict(),
                    "status": "running",
                    "registered": self._is_registered(rt_state.agent_id) if self._db else False,
                })

        return sorted(results, key=lambda a: (a["framework"], a["agent_name"]))

    def register(self, manifest: AgentManifest, workspace_id: str = "") -> dict:
        """Persist agent to governance database."""
        if not self._db:
            raise RuntimeError("No database configured. Call set_database() first.")
        now = datetime.now(timezone.utc).isoformat()
        self._db.agent_register_full(
            agent_id=manifest.agent_id,
            workspace_id=workspace_id,
            agent_name=manifest.agent_name,
            framework=manifest.framework,
            version=manifest.version,
            description=manifest.description,
            upstream_url=manifest.upstream_url,
            model=manifest.model,
            capabilities=json.dumps(manifest.capabilities, ensure_ascii=False),
            registry_config=json.dumps(manifest.registry, ensure_ascii=False),
            governance_config=json.dumps(manifest.governance, ensure_ascii=False),
            config_path=manifest.config_path or "",
            created_at=now,
        )
        return {"agent_id": manifest.agent_id, "status": "registered", "registered_at": now}

    def deregister(self, agent_id: str) -> bool:
        if not self._db:
            raise RuntimeError("No database configured.")
        self.runtime.remove_state(agent_id)
        return self._db.agent_delete(agent_id)

    def _is_registered(self, agent_id: str) -> bool:
        try:
            return self._db.agent_get(agent_id) is not None
        except Exception:
            return False


# 鈹€鈹€ Module-level singleton 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

_registrar: AgentRegistrar | None = None


def get_registrar() -> AgentRegistrar:
    global _registrar
    if _registrar is None:
        _registrar = AgentRegistrar()
    return _registrar
