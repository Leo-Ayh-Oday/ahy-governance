"""Agent heartbeat connector — call heartbeat every 30s for ahy-agent → governance.

Usage:
  py scripts/agent_heartbeat.py AhyAgent

Env vars:
  GOVERNANCE_URL  — governance base URL (default http://127.0.0.1:8080)
"""

import sys
import time
import urllib.request
import json
import os

AGENT_NAME = sys.argv[1] if len(sys.argv) > 1 else "AhyAgent"
BASE = os.environ.get("GOVERNANCE_URL", "http://127.0.0.1:8080")
URL = f"{BASE}/api/health/heartbeat"
INTERVAL = 30

print(f"[heartbeat] Sending heartbeat for '{AGENT_NAME}' to {URL} every {INTERVAL}s")

while True:
    try:
        data = json.dumps({"agent_name": AGENT_NAME, "status": "ok", "latency_ms": 100}).encode()
        req = urllib.request.Request(URL, data=data, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=5)
        print(f"[heartbeat] {json.loads(resp.read()).get('timestamp', 'ok')}")
    except Exception as e:
        print(f"[heartbeat] ERROR: {e}")
    time.sleep(INTERVAL)
