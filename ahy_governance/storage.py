"""
Storage engine for Ahy Governance.

Auto-detects backend from DATABASE_URL env var:
- postgresql://... → PostgresDatabase (storage_pg.py)
- sqlite://path or unset → SQLite Database (this file)

All operational data is workspace-scoped via workspace_id.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any


def create_database(url: str | None = None) -> Any:
    """Factory: returns the right database backend based on DATABASE_URL."""
    if url is None:
        url = os.environ.get("DATABASE_URL", os.environ.get("AHY_DB_PATH", ""))
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        from .storage_pg import PostgresDatabase
        return PostgresDatabase(url)
    return Database(url)


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
            framework TEXT NOT NULL DEFAULT '',
            version TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            upstream_url TEXT NOT NULL DEFAULT '',
            capabilities TEXT NOT NULL DEFAULT '{}',
            registry_config TEXT NOT NULL DEFAULT '{}',
            governance_config TEXT NOT NULL DEFAULT '{}',
            tags TEXT NOT NULL DEFAULT '[]',
            config_path TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'registered',
            last_heartbeat TEXT NOT NULL DEFAULT '',
            pid INTEGER NOT NULL DEFAULT 0,
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

        CREATE TABLE IF NOT EXISTS compliance_reports (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL DEFAULT '',
            report_type TEXT NOT NULL DEFAULT '',
            framework TEXT NOT NULL DEFAULT '',
            compliance_score REAL NOT NULL DEFAULT 0,
            data TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS anomalies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT NOT NULL DEFAULT '',
            anomaly_type TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            severity TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            current_value REAL NOT NULL DEFAULT 0,
            baseline_value REAL NOT NULL DEFAULT 0,
            threshold REAL NOT NULL DEFAULT 0,
            evidence TEXT NOT NULL DEFAULT '{}',
            detected_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_anomaly_ws ON anomalies(workspace_id, detected_at);

        CREATE TABLE IF NOT EXISTS cost_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT NOT NULL DEFAULT '',
            rec_type TEXT NOT NULL,
            priority TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            current_model TEXT NOT NULL DEFAULT '',
            suggested_model TEXT NOT NULL DEFAULT '',
            estimated_savings_usd REAL NOT NULL DEFAULT 0,
            evidence TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_costrec_ws ON cost_recommendations(workspace_id, created_at);

        CREATE TABLE IF NOT EXISTS recovery_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT NOT NULL DEFAULT '',
            agent_name TEXT NOT NULL,
            incident_type TEXT NOT NULL,
            error_message TEXT NOT NULL DEFAULT '',
            recovery_action TEXT NOT NULL DEFAULT '',
            diagnosed_by TEXT NOT NULL DEFAULT 'rule',
            success INTEGER NOT NULL DEFAULT 0,
            confidence REAL NOT NULL DEFAULT 0.0,
            evidence TEXT NOT NULL DEFAULT '{}',
            timestamp TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_rl_agent ON recovery_ledger(agent_name, workspace_id);
        CREATE INDEX IF NOT EXISTS idx_rl_type ON recovery_ledger(incident_type);

        CREATE TABLE IF NOT EXISTS recovery_rules (
            rule_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL,
            incident_type TEXT NOT NULL,
            pattern TEXT NOT NULL DEFAULT '',
            recovery_action TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 50,
            cooldown_seconds INTEGER NOT NULL DEFAULT 300,
            enabled INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS agent_checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT NOT NULL DEFAULT '',
            agent_name TEXT NOT NULL,
            session_id TEXT NOT NULL DEFAULT '',
            state_json TEXT NOT NULL,
            step TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cp_agent_sess ON agent_checkpoints(agent_name, session_id, workspace_id);

        CREATE TABLE IF NOT EXISTS eval_datasets (
            dataset_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            case_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS eval_cases (
            case_id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL,
            input_json TEXT NOT NULL,
            expected_json TEXT,
            tags TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY (dataset_id) REFERENCES eval_datasets(dataset_id)
        );

        CREATE TABLE IF NOT EXISTS eval_runs (
            run_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL DEFAULT '',
            dataset_id TEXT NOT NULL,
            scorers TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)
        self._conn.commit()
        self._migrate_registered_agents()

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

    def _migrate_registered_agents(self):
        """Add AGP columns to existing registered_agents table."""
        agp_columns = {
            "framework": "TEXT NOT NULL DEFAULT ''",
            "version": "TEXT NOT NULL DEFAULT ''",
            "description": "TEXT NOT NULL DEFAULT ''",
            "capabilities": "TEXT NOT NULL DEFAULT '{}'",
            "registry_config": "TEXT NOT NULL DEFAULT '{}'",
            "governance_config": "TEXT NOT NULL DEFAULT '{}'",
            "tags": "TEXT NOT NULL DEFAULT '[]'",
            "config_path": "TEXT NOT NULL DEFAULT ''",
            "status": "TEXT NOT NULL DEFAULT 'registered'",
            "last_heartbeat": "TEXT NOT NULL DEFAULT ''",
            "pid": "INTEGER NOT NULL DEFAULT 0",
        }
        existing = set()
        try:
            cur = self._conn.execute("PRAGMA table_info(registered_agents)")
            existing = {row[1] for row in cur.fetchall()}
        except Exception:
            return
        for col, col_def in agp_columns.items():
            if col not in existing:
                try:
                    self._conn.execute(f"ALTER TABLE registered_agents ADD COLUMN {col} {col_def}")
                except Exception:
                    pass
        # Create AGP indexes (safe to fail if column doesn't exist yet)
        for idx_col in ("framework", "status"):
            try:
                self._conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_ra_{idx_col} ON registered_agents({idx_col})"
                )
            except Exception:
                pass
        self._conn.commit()

        # Make model and upstream_url nullable for AGP compatibility
        if "model" in existing:
            try:
                # SQLite doesn't support ALTER COLUMN, but the new schema is fine —
                # old rows with model set are compatible with DEFAULT '' in new code
                pass
            except Exception:
                pass

    def agent_register(self, agent_id: str, workspace_id: str, agent_name: str,
                        model: str, upstream_url: str, created_at: str,
                        framework: str = "", version: str = "", description: str = "",
                        capabilities: str = "{}", registry_config: str = "{}",
                        governance_config: str = "{}", config_path: str = "") -> None:
        """Backward-compatible wrapper. Prefer agent_register_full for new code."""
        self.agent_register_full(
            agent_id=agent_id, workspace_id=workspace_id, agent_name=agent_name,
            framework=framework, version=version, description=description,
            model=model, upstream_url=upstream_url,
            capabilities=capabilities, registry_config=registry_config,
            governance_config=governance_config, config_path=config_path,
            created_at=created_at,
        )

    def agent_register_full(self, agent_id: str, workspace_id: str, agent_name: str,
                            framework: str = "", version: str = "", description: str = "",
                            model: str = "", upstream_url: str = "",
                            capabilities: str = "{}", registry_config: str = "{}",
                            governance_config: str = "{}", config_path: str = "",
                            created_at: str = "") -> None:
        self._execute(
            "INSERT OR REPLACE INTO registered_agents "
            "(agent_id, workspace_id, agent_name, framework, version, description, "
            "model, upstream_url, capabilities, registry_config, governance_config, "
            "tags, config_path, status, last_heartbeat, pid, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (agent_id, workspace_id, agent_name, framework, version, description,
             model, upstream_url, capabilities, registry_config, governance_config,
             "[]", config_path, "registered", "", 0, created_at),
        )

    def agent_get(self, agent_id: str) -> dict | None:
        return self._fetchone("SELECT * FROM registered_agents WHERE agent_id=?", (agent_id,))

    def agent_list(self, workspace_id: str = "") -> list[dict]:
        rows = self._fetchall(
            "SELECT * FROM registered_agents WHERE workspace_id=? "
            "ORDER BY framework, agent_name",
            (workspace_id,)
        )
        return [dict(r) for r in rows]

    def agent_list_by_status(self, workspace_id: str = "", status: str = "") -> list[dict]:
        if status:
            rows = self._fetchall(
                "SELECT * FROM registered_agents WHERE workspace_id=? AND status=? "
                "ORDER BY framework, agent_name",
                (workspace_id, status)
            )
        else:
            rows = self._fetchall(
                "SELECT * FROM registered_agents WHERE workspace_id=? "
                "ORDER BY framework, agent_name",
                (workspace_id,)
            )
        return [dict(r) for r in rows]

    def agent_update_status(self, agent_id: str, status: str, pid: int = 0) -> bool:
        cur = self._execute(
            "UPDATE registered_agents SET status=?, pid=?, last_heartbeat=? WHERE agent_id=?",
            (status, pid, datetime.now(timezone.utc).isoformat(), agent_id),
        )
        return cur.rowcount > 0

    def agent_heartbeat(self, agent_id: str) -> bool:
        cur = self._execute(
            "UPDATE registered_agents SET last_heartbeat=? WHERE agent_id=?",
            (datetime.now(timezone.utc).isoformat(), agent_id),
        )
        return cur.rowcount > 0

    def agent_list_stale(self, workspace_id: str = "",
                         max_age_seconds: int = 120) -> list[dict]:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)).isoformat()
        rows = self._fetchall(
            "SELECT * FROM registered_agents WHERE workspace_id=? "
            "AND status='running' AND last_heartbeat < ?",
            (workspace_id, cutoff),
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

    # ── Compliance Reports (enterprise stub) ─────────────────

    def compliance_report_insert(self, report_id: str, workspace_id: str,
                                  report_type: str, framework: str,
                                  score: float, data: str) -> None:
        self._execute(
            "INSERT OR REPLACE INTO compliance_reports (id, workspace_id, report_type, framework, compliance_score, data) VALUES (?, ?, ?, ?, ?, ?)",
            (report_id, self._w(workspace_id), report_type, framework, score, data),
        )

    def compliance_report_get(self, report_id: str, workspace_id: str = "") -> dict | None:
        return self._fetchone(
            "SELECT * FROM compliance_reports WHERE id=? AND workspace_id=?",
            (report_id, self._w(workspace_id)),
        )

    def compliance_report_latest(self, report_type: str, workspace_id: str = "") -> dict | None:
        return self._fetchone(
            "SELECT * FROM compliance_reports WHERE report_type=? AND workspace_id=? ORDER BY rowid DESC LIMIT 1",
            (report_type, self._w(workspace_id)),
        )

    def compliance_reports_all(self, workspace_id: str = "") -> list[dict]:
        return self._fetchall(
            "SELECT * FROM compliance_reports WHERE workspace_id=? ORDER BY rowid DESC",
            (self._w(workspace_id),),
        )

    # ── Anomalies ───────────────────────────────────────────

    def anomaly_insert(self, anomaly_type: str, agent_name: str, severity: str,
                       description: str, current_value: float, baseline_value: float,
                       threshold: float, evidence: str, detected_at: str,
                       workspace_id: str = "") -> None:
        self._execute(
            "INSERT INTO anomalies (workspace_id, anomaly_type, agent_name, severity, "
            "description, current_value, baseline_value, threshold, evidence, detected_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (self._w(workspace_id), anomaly_type, agent_name, severity,
             description, current_value, baseline_value, threshold, evidence, detected_at),
        )

    def anomalies_list(self, workspace_id: str = "", limit: int = 100) -> list[dict]:
        return self._fetchall(
            "SELECT * FROM anomalies WHERE workspace_id=? ORDER BY detected_at DESC LIMIT ?",
            (self._w(workspace_id), limit),
        )

    # ── Cost Recommendations ───────────────────────────────────

    def recommendation_insert(self, rec_type: str, priority: str, agent_name: str,
                              description: str, current_model: str, suggested_model: str,
                              estimated_savings_usd: float, evidence: str,
                              created_at: str, workspace_id: str = "") -> None:
        self._execute(
            "INSERT INTO cost_recommendations (workspace_id, rec_type, priority, agent_name, "
            "description, current_model, suggested_model, estimated_savings_usd, evidence, "
            "created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (self._w(workspace_id), rec_type, priority, agent_name,
             description, current_model, suggested_model, estimated_savings_usd,
             evidence, created_at),
        )

    def recommendations_list(self, workspace_id: str = "", limit: int = 100) -> list[dict]:
        return self._fetchall(
            "SELECT * FROM cost_recommendations WHERE workspace_id=? ORDER BY created_at DESC LIMIT ?",
            (self._w(workspace_id), limit),
        )

    # ── Recovery Ledger ────────────────────────────────────────

    def recovery_ledger_insert(self, agent_name: str, incident_type: str,
                               error_message: str, recovery_action: str,
                               diagnosed_by: str, success: bool, confidence: float,
                               evidence: str, timestamp: str, workspace_id: str = "") -> int:
        cur = self._execute(
            "INSERT INTO recovery_ledger (workspace_id, agent_name, incident_type, "
            "error_message, recovery_action, diagnosed_by, success, confidence, "
            "evidence, timestamp) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (self._w(workspace_id), agent_name, incident_type, error_message,
             recovery_action, diagnosed_by, 1 if success else 0, confidence,
             evidence, timestamp),
        )
        return cur.lastrowid

    def recovery_ledger_list(self, agent_name: str = "", incident_type: str = "",
                             workspace_id: str = "", limit: int = 100) -> list[dict]:
        conditions = ["workspace_id=?"]
        params: list = [self._w(workspace_id)]
        if agent_name:
            conditions.append("agent_name=?")
            params.append(agent_name)
        if incident_type:
            conditions.append("incident_type=?")
            params.append(incident_type)
        where = " AND ".join(conditions)
        return self._fetchall(
            f"SELECT * FROM recovery_ledger WHERE {where} ORDER BY timestamp DESC LIMIT ?",
            tuple(params + [limit]),
        )

    def recovery_ledger_similar(self, incident_type: str, error_message: str,
                                workspace_id: str = "", limit: int = 5) -> list[dict]:
        return self._fetchall(
            "SELECT * FROM recovery_ledger WHERE workspace_id=? AND incident_type=? "
            "AND success=1 ORDER BY timestamp DESC LIMIT ?",
            (self._w(workspace_id), incident_type, limit),
        )

    # ── Recovery Rules ─────────────────────────────────────────

    def recovery_rules_list(self, workspace_id: str = "") -> list[dict]:
        return self._fetchall(
            "SELECT * FROM recovery_rules WHERE workspace_id=? ORDER BY priority",
            (self._w(workspace_id),),
        )

    def recovery_rules_upsert(self, rule_id: str, name: str, incident_type: str,
                              pattern: str, recovery_action: str, priority: int,
                              cooldown_seconds: int, enabled: bool,
                              workspace_id: str = "") -> None:
        self._execute(
            "INSERT OR REPLACE INTO recovery_rules (rule_id, workspace_id, name, "
            "incident_type, pattern, recovery_action, priority, cooldown_seconds, enabled) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (rule_id, self._w(workspace_id), name, incident_type,
             pattern, recovery_action, priority, cooldown_seconds,
             1 if enabled else 0),
        )

    # ── Checkpoints ─────────────────────────────────────────

    def checkpoint_insert(self, agent_name: str, session_id: str,
                          state_json: str, step: str, created_at: str,
                          workspace_id: str = "") -> int:
        cur = self._execute(
            "INSERT INTO agent_checkpoints (workspace_id, agent_name, session_id, "
            "state_json, step, created_at) VALUES (?,?,?,?,?,?)",
            (self._w(workspace_id), agent_name, session_id, state_json, step, created_at),
        )
        return cur.lastrowid

    def checkpoint_latest(self, agent_name: str, session_id: str = "",
                          workspace_id: str = "") -> dict | None:
        if session_id:
            return self._fetchone(
                "SELECT * FROM agent_checkpoints WHERE agent_name=? AND session_id=? "
                "AND workspace_id=? ORDER BY created_at DESC LIMIT 1",
                (agent_name, session_id, self._w(workspace_id)),
            )
        return self._fetchone(
            "SELECT * FROM agent_checkpoints WHERE agent_name=? AND workspace_id=? "
            "ORDER BY created_at DESC LIMIT 1",
            (agent_name, self._w(workspace_id)),
        )

    def checkpoint_list(self, agent_name: str = "", session_id: str = "",
                        workspace_id: str = "", limit: int = 50) -> list[dict]:
        conditions = ["workspace_id=?"]
        params: list = [self._w(workspace_id)]
        if agent_name:
            conditions.append("agent_name=?")
            params.append(agent_name)
        if session_id:
            conditions.append("session_id=?")
            params.append(session_id)
        where = " AND ".join(conditions)
        return self._fetchall(
            f"SELECT * FROM agent_checkpoints WHERE {where} ORDER BY created_at DESC LIMIT ?",
            tuple(params + [limit]),
        )

    def checkpoint_prune(self, max_age_days: int, workspace_id: str = "") -> int:
        from datetime import datetime, timezone, timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM agent_checkpoints WHERE workspace_id=? AND created_at < ?",
                (self._w(workspace_id), cutoff),
            )
            self._conn.commit()
            return cur.rowcount

    # ── Eval Datasets ────────────────────────────────────────

    def dataset_insert(self, dataset_id: str, name: str, description: str,
                       case_count: int, workspace_id: str = "") -> None:
        self._execute(
            "INSERT INTO eval_datasets (dataset_id, workspace_id, name, description, case_count, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (dataset_id, self._w(workspace_id), name, description, case_count,
             datetime.now(timezone.utc).isoformat()),
        )

    def dataset_list(self, workspace_id: str = "") -> list[dict]:
        return self._fetchall(
            "SELECT * FROM eval_datasets WHERE workspace_id=? ORDER BY created_at DESC",
            (self._w(workspace_id),),
        )

    def case_insert(self, case_id: str, dataset_id: str, input_json: str,
                    expected_json: str | None, tags: str) -> None:
        self._execute(
            "INSERT INTO eval_cases (case_id, dataset_id, input_json, expected_json, tags) "
            "VALUES (?,?,?,?,?)",
            (case_id, dataset_id, input_json, expected_json, tags),
        )

    def case_list(self, dataset_id: str) -> list[dict]:
        return self._fetchall(
            "SELECT * FROM eval_cases WHERE dataset_id=? ORDER BY case_id",
            (dataset_id,),
        )

    def eval_run_insert(self, run_id: str, dataset_id: str, scorers: str,
                        summary_json: str, workspace_id: str = "") -> None:
        self._execute(
            "INSERT INTO eval_runs (run_id, workspace_id, dataset_id, scorers, summary_json, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (run_id, self._w(workspace_id), dataset_id, scorers, summary_json,
             datetime.now(timezone.utc).isoformat()),
        )

    def eval_run_list(self, dataset_id: str = "", workspace_id: str = "",
                      limit: int = 50) -> list[dict]:
        if dataset_id:
            return self._fetchall(
                "SELECT * FROM eval_runs WHERE workspace_id=? AND dataset_id=? "
                "ORDER BY created_at DESC LIMIT ?",
                (self._w(workspace_id), dataset_id, limit),
            )
        return self._fetchall(
            "SELECT * FROM eval_runs WHERE workspace_id=? ORDER BY created_at DESC LIMIT ?",
            (self._w(workspace_id), limit),
        )

    # ── Lifecycle ───────────────────────────────────────────

    def clear_all(self) -> None:
        tables = [
            "health_heartbeats", "health_calls",
            "cost_entries", "cost_budget",
            "conflicts", "audit_entries",
            "rbac_api_keys", "rbac_users", "rbac_workspaces",
            "memory_entries", "registered_agents",
            "anomalies", "cost_recommendations",
            "recovery_ledger", "recovery_rules",
            "agent_checkpoints",
            "eval_datasets", "eval_cases", "eval_runs",
        ]
        for t in tables:
            self._execute(f"DELETE FROM {t}")

    def close(self) -> None:
        if self._conn:
            self._conn.close()
