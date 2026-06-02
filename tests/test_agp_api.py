import json

from fastapi.testclient import TestClient

from web.server import app


client = TestClient(app)


def agp_manifest(**overrides):
    data = {
        "manifest_version": "1.0",
        "agent_id": "com.example.api-agent",
        "agent_name": "API Agent",
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
    data.update(overrides)
    return data


class TestAgentDiscoverRegister:
    def test_import_candidates_endpoint_is_read_only(self, monkeypatch):
        from ahy_governance.agent_import_scanner import ImportCandidate
        import ahy_governance.agent_import_scanner as scanner

        monkeypatch.setattr(scanner, "scan_import_candidates", lambda roots=None: [
            ImportCandidate(
                candidate_id="ic_test",
                name="Codex CLI",
                kind="codex_config",
                source_path="C:/Users/example/.codex/config.toml",
                confidence="high",
                evidence=["found config.toml"],
            )
        ])

        response = client.get("/api/agent/import-candidates")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["candidates"][0]["registerable"] is False

    def test_requires_explicit_selection(self):
        response = client.post("/api/agent/discover/register", json={})

        assert response.status_code == 400
        assert "agent_ids are required" in response.json()["detail"]

    def test_rejects_missing_selected_agent(self, monkeypatch, tmp_path):
        import web.server as server
        monkeypatch.setattr(server, "_ensure_db", lambda: None)

        import ahy_governance.agent_registry as registry
        monkeypatch.setattr(registry, "scan_filesystem", lambda: [])

        response = client.post(
            "/api/agent/discover/register",
            json={"agent_ids": ["com.example.missing"]},
        )

        assert response.status_code == 404
        assert response.json()["detail"]["missing_agent_ids"] == ["com.example.missing"]

    def test_registers_selected_manifest(self, monkeypatch, tmp_path):
        manifest_path = tmp_path / ".ahy-agent.json"
        manifest_path.write_text(json.dumps(agp_manifest()), encoding="utf-8")

        from ahy_governance.storage import Database
        db = Database(str(tmp_path / "agents.db"))

        import web.server as server
        monkeypatch.setattr(server, "_ensure_db", lambda: db)

        import ahy_governance.agent_registry as registry
        original_scan = registry.scan_filesystem
        monkeypatch.setattr(registry, "scan_filesystem", lambda: original_scan([tmp_path]))

        response = client.post(
            "/api/agent/discover/register",
            json={"agent_ids": ["com.example.api-agent"]},
        )

        assert response.status_code == 200
        assert response.json()["registered"] == 1
        assert db.agent_get("com.example.api-agent")["agent_name"] == "API Agent"

    def test_register_all_requires_explicit_flag(self, monkeypatch, tmp_path):
        manifest_path = tmp_path / ".ahy-agent.json"
        manifest_path.write_text(json.dumps(agp_manifest()), encoding="utf-8")

        from ahy_governance.storage import Database
        db = Database(str(tmp_path / "agents.db"))

        import web.server as server
        monkeypatch.setattr(server, "_ensure_db", lambda: db)

        import ahy_governance.agent_registry as registry
        original_scan = registry.scan_filesystem
        monkeypatch.setattr(registry, "scan_filesystem", lambda: original_scan([tmp_path]))

        response = client.post(
            "/api/agent/discover/register",
            json={"register_all": True},
        )

        assert response.status_code == 200
        assert response.json()["registered"] == 1
