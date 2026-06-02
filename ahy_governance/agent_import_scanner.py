"""Static import-candidate scanner for non-AGP agent components.

This scanner is intentionally read-only. It detects configuration and project
fingerprints that can be converted into AGP manifests later, but it never
executes commands from discovered configs and never registers agents.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .agent_registry import _default_search_roots


@dataclass
class ImportCandidate:
    candidate_id: str
    name: str
    kind: str
    source_path: str
    confidence: str
    evidence: list[str] = field(default_factory=list)
    can_generate_agp: bool = True
    registerable: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ImportCandidateScanner:
    """Find likely local agent components without treating them as AGP agents."""

    def scan(self, roots: list[str | Path] | None = None) -> list[ImportCandidate]:
        candidates: dict[str, ImportCandidate] = {}
        for candidate in self._scan_known_clients():
            candidates.setdefault(candidate.candidate_id, candidate)
        for candidate in self._scan_project_roots(roots):
            candidates.setdefault(candidate.candidate_id, candidate)
        return sorted(candidates.values(), key=lambda c: (c.kind, c.name, c.source_path))

    def _scan_known_clients(self) -> list[ImportCandidate]:
        home = Path.home()
        known_paths = [
            ("Codex CLI", "codex_config", home / ".codex" / "config.toml"),
            ("Codex CLI", "codex_config", home / ".codex" / "config.json"),
            ("Claude MCP", "mcp_config", home / ".claude" / ".mcp.json"),
            ("Claude Desktop MCP", "mcp_config", home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"),
            ("Cursor", "cursor_config", home / ".cursor"),
            ("Windsurf", "windsurf_config", home / ".codeium" / "windsurf"),
            ("Gemini CLI", "gemini_config", home / ".gemini"),
        ]
        results = []
        for name, kind, path in known_paths:
            if not path.exists():
                continue
            evidence = [f"found {path.name}"]
            metadata: dict[str, Any] = {}
            if kind == "mcp_config" and path.is_file():
                metadata.update(_safe_mcp_summary(path))
                if metadata.get("mcp_server_count", 0):
                    evidence.append(f"declares {metadata['mcp_server_count']} MCP servers")
            results.append(_candidate(
                name=name,
                kind=kind,
                source_path=path,
                confidence="high" if kind in ("codex_config", "mcp_config") else "medium",
                evidence=evidence,
                metadata=metadata,
            ))
        return results

    def _scan_project_roots(self, roots: list[str | Path] | None) -> list[ImportCandidate]:
        search_roots = [Path(r).expanduser() for r in roots] if roots is not None else _default_search_roots()
        results: list[ImportCandidate] = []
        seen: set[str] = set()
        for root in search_roots:
            try:
                root = root.resolve()
            except Exception:
                continue
            if not root.is_dir():
                continue
            for project in _iter_project_dirs(root):
                key = str(project)
                if key in seen or (project / ".ahy-agent.json").is_file():
                    continue
                seen.add(key)
                candidate = _project_candidate(project)
                if candidate:
                    results.append(candidate)
        return results


def _candidate(name: str, kind: str, source_path: Path, confidence: str,
               evidence: list[str], metadata: dict[str, Any] | None = None) -> ImportCandidate:
    resolved = str(source_path.resolve())
    raw_id = f"{kind}:{resolved}"
    return ImportCandidate(
        candidate_id="ic_" + hashlib.sha1(raw_id.encode("utf-8")).hexdigest()[:16],
        name=name,
        kind=kind,
        source_path=resolved,
        confidence=confidence,
        evidence=evidence,
        metadata=metadata or {},
    )


def _safe_mcp_summary(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"parse_error": True}
    servers = data.get("mcpServers", {})
    if not isinstance(servers, dict):
        return {"mcp_server_count": 0}
    names = [str(name) for name in servers.keys()]
    return {
        "mcp_server_count": len(names),
        "mcp_server_names": names[:20],
    }


def _iter_project_dirs(root: Path):
    skip_dirs = {
        ".git", ".venv", "venv", "node_modules", "__pycache__", ".next",
        "dist", "build", "target", ".tox", ".pytest_cache",
    }
    stack = [(root, 0)]
    max_depth = int(os.environ.get("AHY_IMPORT_SCAN_DEPTH", "3"))
    while stack:
        current, depth = stack.pop()
        yield current
        if depth == 0 and _project_candidate(current) is not None:
            continue
        if depth >= max_depth:
            continue
        try:
            children = sorted(current.iterdir(), key=lambda p: p.name.lower())
        except PermissionError:
            continue
        for child in children:
            if child.is_dir() and child.name not in skip_dirs and not child.name.startswith("."):
                stack.append((child, depth + 1))


def _project_candidate(project: Path) -> ImportCandidate | None:
    evidence: list[str] = []
    score = 0

    marker_files = {
        "AGENTS.md": 2,
        "SKILL.md": 2,
        ".mcp.json": 3,
        "agent.py": 3,
        "orchestrator.py": 3,
        "workflow.py": 2,
        "server.py": 1,
        "pyproject.toml": 1,
        "requirements.txt": 1,
        "package.json": 1,
    }
    for filename, weight in marker_files.items():
        if (project / filename).is_file():
            score += weight
            evidence.append(f"found {filename}")

    marker_dirs = {
        "skills": 2,
        "tools": 2,
        "sessions": 2,
        "memory": 1,
        "channels": 1,
        "core": 1,
    }
    for dirname, weight in marker_dirs.items():
        if (project / dirname).is_dir():
            score += weight
            evidence.append(f"found {dirname}/")

    nested_markers = {
        Path("config") / "settings.json": 3,
        Path("core") / "orchestrator.py": 3,
    }
    for marker, weight in nested_markers.items():
        if (project / marker).is_file():
            score += weight
            evidence.append(f"found {marker.as_posix()}")

    dependencies = _dependency_hits(project)
    if dependencies:
        score += min(6, len(dependencies) * 2)
        evidence.append("agent dependencies: " + ", ".join(dependencies[:8]))

    if score < 4:
        return None
    if score >= 8:
        confidence = "high"
    elif score >= 5:
        confidence = "medium"
    else:
        confidence = "low"
    return _candidate(
        name=project.name or "Local Agent Project",
        kind="custom_project",
        source_path=project,
        confidence=confidence,
        evidence=evidence,
        metadata={"score": score, "dependency_hits": dependencies},
    )


def _dependency_hits(project: Path) -> list[str]:
    needles = {
        "langgraph", "langchain", "crewai", "autogen", "openai",
        "anthropic", "mcp", "fastapi", "uvicorn", "semantic-kernel",
    }
    files = [project / "pyproject.toml", project / "requirements.txt", project / "package.json"]
    hits: set[str] = set()
    for path in files:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except Exception:
            continue
        for needle in needles:
            if needle in text:
                hits.add(needle)
    return sorted(hits)


_scanner: ImportCandidateScanner | None = None


def get_import_candidate_scanner() -> ImportCandidateScanner:
    global _scanner
    if _scanner is None:
        _scanner = ImportCandidateScanner()
    return _scanner


def scan_import_candidates(roots: list[str | Path] | None = None) -> list[ImportCandidate]:
    return get_import_candidate_scanner().scan(roots)
