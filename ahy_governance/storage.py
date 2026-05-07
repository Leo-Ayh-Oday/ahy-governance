"""
SQLite persistence engine for Ahy Governance (open-source edition).

All operational data is workspace-scoped via workspace_id.
This is a minimal but functional implementation — the enterprise edition
includes advanced features like tmpfs memory disk and SHA-256 audit chains.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from typing import Any


class Database:
    def __init__(self, path: str | None = None):
        if path is None:
            path = os.environ.get("AHY_DB_PATH", "")
        if not path:
            self._conn = None
            self.enabled = False
            return
        self.enabled = True
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._lock = threading.Lock()
        self._init_tables()

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        with self._lock:
            cur = self._conn.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None

    def _fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    def _w(self, ws: str) -> str:
        return ws or ""

    def _init_tables(self):
        c = self._conn
        c.executescript("""
        CREATE TABLE IF NOT EXISTS health_heartbeats (
            agent_name TEXT NOT NULL,
            workspace_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'ok',
            latency_ms REAL NOT NULL DEFAULT 0,
            timestamp TEXT NOT NULL,
            PRIMARY KEY (agent_name, workspace_id)
        );

        CREATE TABLE IF NOT EXISTS health_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            workspace_id TEXT NOT NULL DEFAULT '',
            success INTEGER NOT NULL DEFAULT 1,
            latency_ms REAL NOT NULL DEFAULT 0,
            session_id TEXT NOT NULL DEFAULT '',
            timestamp TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_hc_agent ON health_calls(agent_name, workspace_id);

        CREATE TABLE IF NOT EXISTS cost_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            workspace_id TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL,
            tokens_in INTEGER NOT NULL DEFAULT 0,
            tokens_out INTEGER NOT NULL DEFAULT 0,
            cost_usd REAL NOT NULL DEFAULT 0.0,
            session_id TEXT NOT NULL DEFAULT '',
            timestamp TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cost_budget (
            workspace_id TEXT PRIMARY KEY,
            limit_usd REAL NOT NULL DEFAULT 0,
            period TEXT NOT NULL DEFAULT 'monthly',
            current_usd REAL NOT NULL DEFAULT 0,
            alert_threshold REAL NOT NULL DEFAULT 0.8,
            auto_block INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS conflicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT NOT NULL DEFAULT '',
            conflict_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            agents_involved TEXT NOT NULL DEFAULT '[]',
            description TEXT NOT NULL DEFAULT '',
            evidence TEXT NOT NULL DEFAULT '{}',
            suggestion TEXT NOT NULL DEFAULT '',
            detected_at TEXT NOT NULL,
            resolution_status TEXT NOT NULL DEFAULT 'open'
        );

        CREATE TABLE IF NOT EXISTS rbac_workspaces (
            workspace_id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            owner_user_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rbac_users (
            user_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            created_at TEXT NOT NULL,
            PRIMARY KEY (user_id, workspace_id)
        );

        CREATE TABLE IF NOT EXISTS rbac_api_keys (
            key_id TEXT PRIMARY KEY,
            key_hash TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT 'viewer',
            workspace_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            revoked INTEGER NOT NULL DEFAULT 0,
            last_used TEXT
        );

        CREATE TABLE IF NOT EXISTS registered_agents (
            agent_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL DEFAULT '',
            agent_name TEXT NOT NULL,
            model TEXT NOT NULL,
            upstream_url TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ra_ws ON registered_agents(workspace_id);

        CREATE TABLE IF NOT EXISTS audit_entries (
            idx INTEGER NOT NULL,
            workspace_id TEXT NOT NULL DEFAULT '',
            event_type TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '{}',
            session_id TEXT NOT NULL DEFAULT '',
            timestamp TEXT NOT NULL,
            hash TEXT NOT NULL,
            prev_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_entries (
            namespace TEXT NOT NULL,
            key TEXT NOT NULL,
            workspace_id TEXT NOT NULL DEFAULT '',
            value TEXT NOT NULL DEFAULT '',
            source_agent TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '[]',
            created_at REAL NOT NULL,
            ttl_seconds REAL,
            access_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (namespace, key, workspace_id)
        );
        """)
        self._conn.commit()

    # ── Health ──────────────────────────────────────────────

    def heartbeat_upsert(self, agent_name: str, status: str, latency_ms: float,
                          timestamp: str, workspace_id: str = "") -> None:
        self._execute(
            "INSERT INTO health_heartbeats (agent_name, workspace_id, status, latency_ms, timestamp) "
            "VALUES (?,?,?,?,?) ON CONFLICT(agent_name, workspace_id) DO UPDATE SET "
            "status=excluded.status, latency_ms=excluded.latency_ms, timestamp=excluded.timestamp",
            (agent_name, self._w(workspace_id), status, latency_ms, timestamp),
        )

    def heartbeat_get(self, agent_name: str, workspace_id: str = "") -> dict | None:
        return self._fetchone(
            "SELECT * FROM health_heartbeats WHERE agent_name=? AND workspace_id=?",
            (agent_name, self._w(workspace_id)),
        )

    def heartbeat_all(self, workspace_id: str = "") -> list[dict]:
        return self._fetchall(
            "SELECT * FROM health_heartbeats WHERE workspace_id=?", (self._w(workspace_id),)
        )

    def heartbeat_delete(self, agent_name: str, workspace_id: str = "") -> None:
        self._execute(
            "DELETE FROM health_heartbeats WHERE agent_name=? AND workspace_id=?",
            (agent_name, self._w(workspace_id)),
        )

    def call_insert(self, agent_name: str, success: bool, latency_ms: float,
                     session_id: str, timestamp: str, workspace_id: str = "") -> int:
        cur = self._execute(
            "INSERT INTO health_calls (agent_name, workspace_id, success, latency_ms, session_id, timestamp) "
            "VALUES (?,?,?,?,?,?)",
            (agent_name, self._w(workspace_id), 1 if success else 0, latency_ms, session_id, timestamp),
        )
        return cur.lastrowid

    def calls_by_agent(self, agent_name: str, limit: int = 500, workspace_id: str = "") -> list[dict]:
        return self._fetchall(
            "SELECT * FROM health_calls WHERE agent_name=? AND workspace_id=? ORDER BY timestamp DESC LIMIT ?",
            (agent_name, self._w(workspace_id), limit),
        )

    def calls_count_by_agent(self, agent_name: str, workspace_id: str = "") -> int:
        r = self._fetchone(
            "SELECT COUNT(*) as cnt FROM health_calls WHERE agent_name=? AND workspace_id=?",
            (agent_name, self._w(workspace_id)),
        )
        return r["cnt"] if r else 0

    def calls_success_count(self, agent_name: str, workspace_id: str = "") -> int:
        r = self._fetchone(
            "SELECT COUNT(*) as cnt FROM health_calls WHERE agent_name=? AND workspace_id=? AND success=1",
            (agent_name, self._w(workspace_id)),
        )
        return r["cnt"] if r else 0

    def calls_latencies(self, agent_name: str, limit: int = 500, workspace_id: str = "") -> list[float]:
        rows = self._fetchall(
            "SELECT latency_ms FROM health_calls WHERE agent_name=? AND workspace_id=? ORDER BY timestamp DESC LIMIT ?",
            (agent_name, self._w(workspace_id), limit),
        )
        return [r["latency_ms"] for r in rows]

    def calls_all_agents(self, workspace_id: str = "") -> list[str]:
        rows = self._fetchall(
            "SELECT DISTINCT agent_name FROM health_calls WHERE workspace_id=?", (self._w(workspace_id),)
        )
        return [r["agent_name"] for r in rows]

    # ── Cost ────────────────────────────────────────────────

    def cost_insert(self, agent_name: str, model: str, tokens_in: int, tokens_out: int,
                    cost_usd: float, session_id: str, timestamp: str,
                    workspace_id: str = "") -> int:
        cur = self._execute(
            "INSERT INTO cost_entries (agent_name, workspace_id, model, tokens_in, tokens_out, cost_usd, session_id, timestamp) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (agent_name, self._w(workspace_id), model, tokens_in, tokens_out, cost_usd, session_id, timestamp),
        )
        return cur.lastrowid

    def cost_all(self, workspace_id: str = "") -> list[dict]:
        return self._fetchall(
            "SELECT * FROM cost_entries WHERE workspace_id=? ORDER BY timestamp DESC",
            (self._w(workspace_id),),
        )

    def cost_by_agent(self, agent_name: str, workspace_id: str = "") -> list[dict]:
        return self._fetchall(
            "SELECT * FROM cost_entries WHERE agent_name=? AND workspace_id=? ORDER BY timestamp DESC",
            (agent_name, self._w(workspace_id)),
        )

    def cost_total_usd(self, workspace_id: str = "") -> float:
        r = self._fetchone(
            "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM cost_entries WHERE workspace_id=?",
            (self._w(workspace_id),),
        )
        return r["total"] if r else 0.0

    def cost_token_totals(self, workspace_id: str = "") -> dict:
        r = self._fetchone(
            "SELECT COALESCE(SUM(tokens_in),0) as tokens_in, COALESCE(SUM(tokens_out),0) as tokens_out "
            "FROM cost_entries WHERE workspace_id=?", (self._w(workspace_id),),
        )
        if r:
            return {"tokens_in": r["tokens_in"], "tokens_out": r["tokens_out"],
                    "tokens_total": r["tokens_in"] + r["tokens_out"]}
        return {"tokens_in": 0, "tokens_out": 0, "tokens_total": 0}

    def budget_get(self, workspace_id: str = "") -> dict | None:
        return self._fetchone("SELECT * FROM cost_budget WHERE workspace_id=?", (self._w(workspace_id),))

    def budget_upsert(self, limit_usd: float, period: str, current_usd: float,
                       alert_threshold: float, auto_block: bool, workspace_id: str = "") -> None:
        ws = self._w(workspace_id)
        self._execute(
            "INSERT INTO cost_budget (workspace_id, limit_usd, period, current_usd, alert_threshold, auto_block) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(workspace_id) DO UPDATE SET "
            "limit_usd=excluded.limit_usd, period=excluded.period, "
            "alert_threshold=excluded.alert_threshold, auto_block=excluded.auto_block",
            (ws, limit_usd, period, current_usd, alert_threshold, 1 if auto_block else 0),
        )

    def budget_update_current(self, amount_usd: float, workspace_id: str = "") -> None:
        self._execute(
            "UPDATE cost_budget SET current_usd = current_usd + ? WHERE workspace_id=?",
            (amount_usd, self._w(workspace_id)),
        )

    # ── Conflicts ───────────────────────────────────────────

    def conflict_insert(self, conflict_type: str, severity: str, agents_involved: str,
                        description: str, evidence: str, suggestion: str, detected_at: str,
                        workspace_id: str = "") -> int:
        cur = self._execute(
            "INSERT INTO conflicts (workspace_id, conflict_type, severity, agents_involved, description, evidence, suggestion, detected_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (self._w(workspace_id), conflict_type, severity, agents_involved, description, evidence, suggestion, detected_at),
        )
        return cur.lastrowid

    def conflicts_all(self, workspace_id: str = "") -> list[dict]:
        return self._fetchall(
            "SELECT * FROM conflicts WHERE workspace_id=? ORDER BY detected_at DESC", (self._w(workspace_id),)
        )

    def conflicts_count(self, workspace_id: str = "") -> int:
        r = self._fetchone("SELECT COUNT(*) as cnt FROM conflicts WHERE workspace_id=?", (self._w(workspace_id),))
        return r["cnt"] if r else 0

    # ── RBAC ────────────────────────────────────────────────

    def workspace_insert(self, ws_id: str, name: str, owner_user_id: str, created_at: str) -> None:
        self._execute(
            "INSERT INTO rbac_workspaces (workspace_id, name, owner_user_id, created_at) VALUES (?,?,?,?)",
            (ws_id, name, owner_user_id, created_at),
        )

    def workspace_get(self, ws_id: str) -> dict | None:
        row = self._fetchone("SELECT * FROM rbac_workspaces WHERE workspace_id=?", (ws_id,))
        if not row:
            row = self._fetchone("SELECT * FROM rbac_workspaces WHERE name=?", (ws_id,))
        return row

    def workspace_all(self) -> list[dict]:
        return self._fetchall("SELECT * FROM rbac_workspaces")

    def rbac_user_insert(self, user_id: str, workspace_id: str, role: str, created_at: str) -> None:
        self._execute(
            "INSERT INTO rbac_users (user_id, workspace_id, role, created_at) VALUES (?,?,?,?)",
            (user_id, workspace_id, role, created_at),
        )

    def apikey_insert(self, key_id: str, key_hash: str, name: str, role: str,
                       workspace_id: str, created_at: str, expires_at: str | None) -> None:
        self._execute(
            "INSERT INTO rbac_api_keys (key_id, key_hash, name, role, workspace_id, created_at, expires_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (key_id, key_hash, name, role, workspace_id, created_at, expires_at),
        )

    def apikey_get_by_hash(self, key_hash: str) -> dict | None:
        return self._fetchone("SELECT * FROM rbac_api_keys WHERE key_hash=?", (key_hash,))

    # ── Registered Agents ───────────────────────────────────

    def agent_register(self, agent_id: str, workspace_id: str, agent_name: str,
                        model: str, upstream_url: str, created_at: str) -> None:
        self._execute(
            "INSERT INTO registered_agents (agent_id, workspace_id, agent_name, model, upstream_url, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (agent_id, workspace_id, agent_name, model, upstream_url, created_at),
        )

    def agent_get(self, agent_id: str) -> dict | None:
        return self._fetchone("SELECT * FROM registered_agents WHERE agent_id=?", (agent_id,))

    def agent_list(self, workspace_id: str = "") -> list[dict]:
        rows = self._fetchall(
            "SELECT agent_id, workspace_id, agent_name, model, upstream_url, created_at FROM registered_agents WHERE workspace_id=?",
            (workspace_id,)
        )
        return [dict(r) for r in rows]

    def agent_delete(self, agent_id: str) -> bool:
        cur = self._execute("DELETE FROM registered_agents WHERE agent_id=?", (agent_id,))
        return cur.rowcount > 0

    # ── Audit ───────────────────────────────────────────────

    def audit_insert(self, idx: int, event_type: str, agent_name: str, details: str,
                     session_id: str, timestamp: str, hash_val: str, prev_hash: str,
                     workspace_id: str = "") -> None:
        self._execute(
            "INSERT INTO audit_entries (idx, workspace_id, event_type, agent_name, details, session_id, timestamp, hash, prev_hash) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (idx, self._w(workspace_id), event_type, agent_name, details, session_id, timestamp, hash_val, prev_hash),
        )

    def audit_all(self, workspace_id: str = "") -> list[dict]:
        return self._fetchall(
            "SELECT * FROM audit_entries WHERE workspace_id=? ORDER BY idx ASC", (self._w(workspace_id),)
        )

    def audit_count(self, workspace_id: str = "") -> int:
        r = self._fetchone("SELECT COUNT(*) as cnt FROM audit_entries WHERE workspace_id=?", (self._w(workspace_id),))
        return r["cnt"] if r else 0

    # ── Memory ──────────────────────────────────────────────

    def memory_upsert(self, namespace: str, key: str, value: str, source_agent: str,
                       tags: str, created_at: float, ttl_seconds: float | None,
                       workspace_id: str = "") -> None:
        ws = self._w(workspace_id)
        self._execute(
            "INSERT INTO memory_entries (namespace, key, workspace_id, value, source_agent, tags, created_at, ttl_seconds) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(namespace, key, workspace_id) DO UPDATE SET "
            "value=excluded.value, source_agent=excluded.source_agent, tags=excluded.tags, "
            "created_at=excluded.created_at, ttl_seconds=excluded.ttl_seconds, access_count=0",
            (namespace, key, ws, value, source_agent, tags, created_at, ttl_seconds),
        )

    def memory_get(self, namespace: str, key: str, workspace_id: str = "") -> dict | None:
        row = self._fetchone(
            "SELECT * FROM memory_entries WHERE namespace=? AND key=? AND workspace_id=?",
            (namespace, key, self._w(workspace_id)),
        )
        return row

    # ── Lifecycle ───────────────────────────────────────────

    def clear_all(self) -> None:
        tables = [
            "health_heartbeats", "health_calls",
            "cost_entries", "cost_budget",
            "conflicts", "audit_entries",
            "rbac_api_keys", "rbac_users", "rbac_workspaces",
            "memory_entries", "registered_agents",
        ]
        for t in tables:
            self._execute(f"DELETE FROM {t}")

    def close(self) -> None:
        if self._conn:
            self._conn.close()
