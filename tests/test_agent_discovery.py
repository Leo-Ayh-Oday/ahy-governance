import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ahy_governance.agent_discovery import _scan_agp_files


def agp_manifest(port: int):
    return {
        "manifest_version": "1.0",
        "agent_id": "local.test-agent",
        "agent_name": "Test Agent",
        "framework": "custom",
        "version": "1.0.0",
        "upstream_url": f"http://127.0.0.1:{port}",
        "model": "unknown",
        "capabilities": {
            "can_read": True,
            "can_search": False,
            "can_write_local": False,
        },
        "registry": {
            "enabled": True,
            "heartbeat_seconds": 30,
        },
    }


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        return


def test_agp_manifest_probe_marks_agent_verified(monkeypatch, tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_port
        (tmp_path / ".ahy-agent.json").write_text(
            json.dumps(agp_manifest(port)),
            encoding="utf-8",
        )

        import ahy_governance.agent_discovery as discovery
        original_scan = discovery.scan_filesystem
        monkeypatch.setattr(discovery, "scan_filesystem", lambda: original_scan([tmp_path]))

        agents = _scan_agp_files()

        assert len(agents) == 1
        assert agents[0].status == "verified"
        assert agents[0].port == port
        assert agents[0].governance["runtime_probe"]["probe_path"] == "/health"
    finally:
        server.shutdown()
        server.server_close()
