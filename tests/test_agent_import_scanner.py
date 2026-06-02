import json

from ahy_governance.agent_import_scanner import ImportCandidateScanner, scan_import_candidates


def test_scans_known_codex_config_without_registering(monkeypatch, tmp_path):
    home = tmp_path / "home"
    codex = home / ".codex"
    codex.mkdir(parents=True)
    (codex / "config.toml").write_text("model = 'gpt-5-codex'\n", encoding="utf-8")
    monkeypatch.setattr("pathlib.Path.home", lambda: home)

    candidates = ImportCandidateScanner().scan(roots=[])

    assert len(candidates) == 1
    assert candidates[0].kind == "codex_config"
    assert candidates[0].confidence == "high"
    assert candidates[0].registerable is False
    assert candidates[0].can_generate_agp is True


def test_summarizes_mcp_config_without_executing_commands(monkeypatch, tmp_path):
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    (claude / ".mcp.json").write_text(json.dumps({
        "mcpServers": {
            "dangerous": {
                "command": "do-not-run-this",
                "args": ["--secret"],
            }
        }
    }), encoding="utf-8")
    monkeypatch.setattr("pathlib.Path.home", lambda: home)

    candidates = ImportCandidateScanner().scan(roots=[])

    assert len(candidates) == 1
    assert candidates[0].kind == "mcp_config"
    assert candidates[0].metadata["mcp_server_count"] == 1
    assert candidates[0].metadata["mcp_server_names"] == ["dangerous"]
    assert "command" not in json.dumps(candidates[0].to_dict()).lower()


def test_detects_custom_project_by_fingerprint(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    project = tmp_path / "my-agent"
    project.mkdir()
    (project / "AGENTS.md").write_text("# Agent\n", encoding="utf-8")
    (project / "agent.py").write_text("print('hi')\n", encoding="utf-8")
    (project / "requirements.txt").write_text("langgraph\nopenai\n", encoding="utf-8")

    candidates = scan_import_candidates([tmp_path])

    assert len(candidates) == 1
    assert candidates[0].kind == "custom_project"
    assert candidates[0].confidence == "high"
    assert "langgraph" in candidates[0].metadata["dependency_hits"]


def test_ignores_existing_agp_project(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    project = tmp_path / "agp-agent"
    project.mkdir()
    (project / ".ahy-agent.json").write_text("{}", encoding="utf-8")
    (project / "AGENTS.md").write_text("# Agent\n", encoding="utf-8")
    (project / "agent.py").write_text("print('hi')\n", encoding="utf-8")

    assert scan_import_candidates([tmp_path]) == []


def test_low_signal_project_is_not_candidate(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    project = tmp_path / "plain-app"
    project.mkdir()
    (project / "server.py").write_text("print('hi')\n", encoding="utf-8")

    assert scan_import_candidates([tmp_path]) == []


def test_parent_agent_workspace_wins_over_downloaded_child_project(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: home)

    ahy = tmp_path / "Ahy Agent"
    ahy.mkdir()
    (ahy / "agent.py").write_text("print('agent')\n", encoding="utf-8")
    (ahy / "config").mkdir()
    (ahy / "config" / "settings.json").write_text("{}", encoding="utf-8")
    (ahy / "core").mkdir()
    (ahy / "core" / "orchestrator.py").write_text("class Orchestrator: pass\n", encoding="utf-8")
    for dirname in ("skills", "tools", "sessions"):
        (ahy / dirname).mkdir()

    openmanus = ahy / "OpenManus"
    openmanus.mkdir()
    (openmanus / "requirements.txt").write_text("openai\nfastapi\nuvicorn\nmcp\n", encoding="utf-8")

    candidates = scan_import_candidates([ahy])

    assert len(candidates) == 1
    assert candidates[0].name == "Ahy Agent"
    assert candidates[0].confidence == "high"
