"""Tests for AGP, the Agent Governance Protocol registry module."""

import json
from pathlib import Path

import pytest

from ahy_governance.agent_registry import (
    AGP_SCHEMA,
    AGPValidationError,
    AgentManifest,
    AgentRegistrar,
    RuntimeRegistry,
    _default_search_roots,
    load_manifest,
    scan_filesystem,
    validate_manifest,
)


def agp_manifest(**overrides):
    data = {
        "manifest_version": "1.0",
        "agent_id": "com.example.test-agent",
        "agent_name": "Test Agent",
        "framework": "custom",
        "version": "1.0.0",
        "upstream_url": "http://localhost:8000",
        "model": "deepseek-chat",
        "capabilities": {
            "can_read": True,
            "can_search": True,
            "can_write_local": False,
        },
        "registry": {
            "enabled": True,
            "heartbeat_seconds": 30,
        },
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key] = {**data[key], **value}
        else:
            data[key] = value
    return data


class TestSchemaValidation:
    def test_valid_minimal_agp_manifest(self):
        assert validate_manifest(agp_manifest()) == []

    def test_missing_required_field(self):
        data = agp_manifest()
        data.pop("manifest_version")
        with pytest.raises(AGPValidationError, match="manifest_version"):
            validate_manifest(data)

    def test_invalid_upstream_url(self):
        with pytest.raises(AGPValidationError, match="upstream_url"):
            validate_manifest(agp_manifest(upstream_url="localhost:8000"))

    def test_heartbeat_too_low(self):
        with pytest.raises(AGPValidationError, match="heartbeat_seconds"):
            validate_manifest(agp_manifest(registry={"heartbeat_seconds": 2}))

    def test_unknown_framework_warns_but_remains_valid(self):
        warnings = validate_manifest(agp_manifest(framework="my-custom-fw"))
        assert len(warnings) == 1
        assert "Unknown framework" in warnings[0]

    def test_rejects_auth_secret_material(self):
        with pytest.raises(AGPValidationError, match="auth.api_key"):
            validate_manifest(agp_manifest(auth={"type": "api_key", "api_key": "secret"}))


class TestLoadManifest:
    def test_load_from_file_preserves_explicit_agent_id(self, tmp_path):
        p = tmp_path / ".ahy-agent.json"
        p.write_text(json.dumps(agp_manifest(agent_id="com.acme.file-agent")), encoding="utf-8")

        manifest = load_manifest(p)

        assert manifest.agent_id == "com.acme.file-agent"
        assert manifest.manifest_version == "1.0"
        assert manifest.agent_name == "Test Agent"
        assert manifest.config_path == str(p.resolve())

    def test_auto_register_defaults_false(self, tmp_path):
        p = tmp_path / ".ahy-agent.json"
        data = agp_manifest()
        data["registry"].pop("auto_register", None)
        p.write_text(json.dumps(data), encoding="utf-8")

        manifest = load_manifest(p)

        assert manifest.auto_register is False
        assert manifest.enabled is True
        assert manifest.heartbeat_seconds == 30

    def test_agent_id_fallback_is_stable(self):
        m1 = AgentManifest(agent_name="Stable", framework="ahy", version="1.0")
        m2 = AgentManifest(agent_name="Stable", framework="ahy", version="2.0")
        assert m1.agent_id == m2.agent_id


class TestScanFilesystem:
    def test_discovers_manifest_in_root(self, tmp_path):
        (tmp_path / ".ahy-agent.json").write_text(json.dumps(agp_manifest()), encoding="utf-8")
        manifests = scan_filesystem([tmp_path])
        assert len(manifests) == 1
        assert manifests[0].agent_name == "Test Agent"

    def test_discovers_manifest_in_subdir(self, tmp_path):
        sub = tmp_path / "my-agent"
        sub.mkdir()
        (sub / ".ahy-agent.json").write_text(
            json.dumps(agp_manifest(agent_id="com.example.sub", agent_name="Sub Agent")),
            encoding="utf-8",
        )
        names = [m.agent_name for m in scan_filesystem([tmp_path])]
        assert "Sub Agent" in names

    def test_skips_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules" / "some-agent"
        nm.mkdir(parents=True)
        (nm / ".ahy-agent.json").write_text(json.dumps(agp_manifest()), encoding="utf-8")
        assert scan_filesystem([tmp_path]) == []

    def test_skips_disabled_agent(self, tmp_path):
        (tmp_path / ".ahy-agent.json").write_text(
            json.dumps(agp_manifest(registry={"enabled": False})),
            encoding="utf-8",
        )
        assert scan_filesystem([tmp_path]) == []

    def test_deduplicates_by_agent_id(self, tmp_path):
        d1 = tmp_path / "loc1"
        d2 = tmp_path / "loc2"
        d1.mkdir()
        d2.mkdir()
        data = agp_manifest(agent_id="com.example.dup", agent_name="Dup")
        (d1 / ".ahy-agent.json").write_text(json.dumps(data), encoding="utf-8")
        (d2 / ".ahy-agent.json").write_text(json.dumps(data), encoding="utf-8")
        assert len(scan_filesystem([d1, d2])) == 1

    def test_invalid_json_skipped(self, tmp_path):
        (tmp_path / ".ahy-agent.json").write_text("not json", encoding="utf-8")
        assert scan_filesystem([tmp_path]) == []

    def test_default_roots_do_not_include_documents(self, monkeypatch, tmp_path):
        monkeypatch.delenv("AHY_AGP_SEARCH_ROOTS", raising=False)
        monkeypatch.chdir(tmp_path)

        roots = {p.name for p in _default_search_roots()}

        assert "Documents" not in roots
        assert tmp_path.resolve() in _default_search_roots()


class TestRuntimeRegistry:
    def test_write_and_read_state(self, tmp_path):
        rr = RuntimeRegistry(tmp_path)
        state = rr.write_state(
            agent_id="test-1", agent_name="Test", framework="ahy",
            version="1.0.0", upstream_url="http://localhost:8000",
            model="gpt-4", pid=12345, port=8000,
        )
        assert state.agent_id == "test-1"
        assert state.status == "running"
        assert state.pid == 12345
        assert rr.read_state("test-1").port == 8000

    def test_heartbeat_updates_timestamp(self, tmp_path):
        rr = RuntimeRegistry(tmp_path)
        rr.write_state("hb-1", "HB", "ahy", "1.0", "http://localhost:8000", "gpt-4")
        import time
        time.sleep(0.1)
        assert rr.heartbeat("hb-1")
        state = rr.read_state("hb-1")
        assert state.last_heartbeat != state.started_at

    def test_scan_stale(self, tmp_path):
        rr = RuntimeRegistry(tmp_path)
        rr.write_state("old-1", "Old", "ahy", "1.0", "http://localhost:8000", "gpt-4")
        from datetime import datetime, timedelta, timezone
        state = rr.read_state("old-1")
        state.last_heartbeat = (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat()
        rr.state_path("old-1").write_text(json.dumps(state.to_dict()), encoding="utf-8")

        stale = rr.scan_stale(max_heartbeat_age_seconds=120)

        assert len(stale) == 1
        assert stale[0].agent_id == "old-1"


class TestAgentRegistrar:
    def test_discover_merges_manifest_and_runtime(self, tmp_path, monkeypatch):
        manifest_path = tmp_path / ".ahy-agent.json"
        manifest_path.write_text(json.dumps(agp_manifest()), encoding="utf-8")

        rr = RuntimeRegistry(tmp_path / "registry")
        rr.write_state(
            agent_id="com.example.test-agent", agent_name="Test Agent", framework="custom",
            version="1.0.0", upstream_url="http://localhost:8000", model="deepseek-chat",
            pid=100, port=8000,
        )

        import ahy_governance.agent_registry as mod
        monkeypatch.setattr(mod, "scan_filesystem", lambda: scan_filesystem([tmp_path]))

        registrar = AgentRegistrar()
        registrar.runtime = rr
        results = registrar.discover()

        assert len(results) == 1
        assert results[0]["agent_id"] == "com.example.test-agent"
        assert results[0]["runtime"]["pid"] == 100

    def test_deregister_removes_runtime_and_db(self, tmp_path):
        from ahy_governance.storage import Database
        db = Database(str(tmp_path / "test.db"))

        rr = RuntimeRegistry(tmp_path / "registry")
        rr.write_state("dereg-1", "Dereg", "ahy", "1.0", "http://localhost:8000", "gpt-4")
        db.agent_register_full(
            agent_id="dereg-1", workspace_id="", agent_name="Dereg",
            framework="ahy", version="1.0", created_at="2024-01-01T00:00:00",
        )

        registrar = AgentRegistrar(db)
        registrar.runtime = rr

        assert registrar.deregister("dereg-1")
        assert db.agent_get("dereg-1") is None
        assert rr.read_state("dereg-1") is None


class TestAGPSchema:
    def test_schema_is_canonical_agp_1_manifest(self):
        assert AGP_SCHEMA["properties"]["manifest_version"]["const"] == "1.0"
        assert "manifest_version" in AGP_SCHEMA["required"]
        assert "upstream_url" in AGP_SCHEMA["required"]
        assert "capabilities" in AGP_SCHEMA["required"]
        assert "registry" in AGP_SCHEMA["required"]

    def test_schema_includes_protocol_capabilities(self):
        caps = AGP_SCHEMA["properties"]["capabilities"]["properties"]
        assert "can_read" in caps
        assert "can_search" in caps
        assert "can_write_local" in caps
        assert "can_execute_shell" in caps
        assert "can_call_network" in caps

    def test_schema_defaults_do_not_auto_register(self):
        reg = AGP_SCHEMA["properties"]["registry"]["properties"]
        assert reg["auto_register"]["default"] is False
