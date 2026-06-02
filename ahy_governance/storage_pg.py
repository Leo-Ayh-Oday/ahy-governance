"""
PostgreSQL persistence engine for Ahy Governance.

Drop-in replacement for storage.Database using SQLAlchemy + psycopg2.
Activated when DATABASE_URL env var is set to a postgresql:// URL.

Usage:
    db = PostgresDatabase("postgresql://user:pass@localhost:5432/ahy_governance")
    # Same interface as storage.Database
    db.heartbeat_upsert("Planner", "ok", 120, now, "ws-1")
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import (
    Column, Integer, Float, Text, create_engine, Index,
    MetaData, Table, text,
)
from sqlalchemy.engine import Engine


class PostgresDatabase:
    def __init__(self, url: str | None = None):
        if url is None:
            url = os.environ.get("DATABASE_URL", "")
        if not url or not url.startswith("postgresql://"):
            self._engine: Engine | None = None
            self.enabled = False
            return

        self.enabled = True
        self._engine = create_engine(
            url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
        self._metadata = MetaData()
        self._define_tables()
        self._metadata.create_all(self._engine)

    def _define_tables(self):
        m = self._metadata

        Table("health_heartbeats", m,
            Column("agent_name", Text, nullable=False),
            Column("workspace_id", Text, nullable=False, default=""),
            Column("status", Text, nullable=False, default="ok"),
            Column("latency_ms", Float, nullable=False, default=0),
            Column("timestamp", Text, nullable=False),
        )

        Table("health_calls", m,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("agent_name", Text, nullable=False),
            Column("workspace_id", Text, nullable=False, default=""),
            Column("success", Integer, nullable=False, default=1),
            Column("latency_ms", Float, nullable=False, default=0),
            Column("session_id", Text, nullable=False, default=""),
            Column("timestamp", Text, nullable=False),
        )
        Index("idx_hc_agent", "agent_name", "workspace_id")

        Table("cost_entries", m,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("agent_name", Text, nullable=False),
            Column("workspace_id", Text, nullable=False, default=""),
            Column("model", Text, nullable=False),
            Column("tokens_in", Integer, nullable=False, default=0),
            Column("tokens_out", Integer, nullable=False, default=0),
            Column("cost_usd", Float, nullable=False, default=0.0),
            Column("session_id", Text, nullable=False, default=""),
            Column("timestamp", Text, nullable=False),
        )

        Table("cost_budget", m,
            Column("workspace_id", Text, primary_key=True),
            Column("limit_usd", Float, nullable=False, default=0),
            Column("period", Text, nullable=False, default="monthly"),
            Column("current_usd", Float, nullable=False, default=0),
            Column("alert_threshold", Float, nullable=False, default=0.8),
            Column("auto_block", Integer, nullable=False, default=1),
        )

        Table("conflicts", m,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("workspace_id", Text, nullable=False, default=""),
            Column("conflict_type", Text, nullable=False),
            Column("severity", Text, nullable=False),
            Column("agents_involved", Text, nullable=False, default="[]"),
            Column("description", Text, nullable=False, default=""),
            Column("evidence", Text, nullable=False, default="{}"),
            Column("suggestion", Text, nullable=False, default=""),
            Column("detected_at", Text, nullable=False),
            Column("resolution_status", Text, nullable=False, default="open"),
        )

        Table("rbac_workspaces", m,
            Column("workspace_id", Text, primary_key=True),
            Column("name", Text, nullable=False, unique=True),
            Column("owner_user_id", Text, nullable=False),
            Column("created_at", Text, nullable=False),
        )

        Table("rbac_users", m,
            Column("user_id", Text, nullable=False),
            Column("workspace_id", Text, nullable=False),
            Column("role", Text, nullable=False, default="viewer"),
            Column("created_at", Text, nullable=False),
        )

        Table("rbac_api_keys", m,
            Column("key_id", Text, primary_key=True),
            Column("key_hash", Text, nullable=False, unique=True),
            Column("name", Text, nullable=False, default=""),
            Column("role", Text, nullable=False, default="viewer"),
            Column("workspace_id", Text, nullable=False),
            Column("created_at", Text, nullable=False),
            Column("expires_at", Text),
            Column("revoked", Integer, nullable=False, default=0),
            Column("last_used", Text),
        )

        Table("registered_agents", m,
            Column("agent_id", Text, primary_key=True),
            Column("workspace_id", Text, nullable=False, default=""),
            Column("agent_name", Text, nullable=False),
            Column("framework", Text, nullable=False, default=""),
            Column("version", Text, nullable=False, default=""),
            Column("description", Text, nullable=False, default=""),
            Column("model", Text, nullable=False, default=""),
            Column("upstream_url", Text, nullable=False, default=""),
            Column("capabilities", Text, nullable=False, default="{}"),
            Column("registry_config", Text, nullable=False, default="{}"),
            Column("governance_config", Text, nullable=False, default="{}"),
            Column("tags", Text, nullable=False, default="[]"),
            Column("config_path", Text, nullable=False, default=""),
            Column("status", Text, nullable=False, default="registered"),
            Column("last_heartbeat", Text, nullable=False, default=""),
            Column("pid", Integer, nullable=False, default=0),
            Column("created_at", Text, nullable=False),
        )
        Index("idx_ra_ws", "workspace_id")

        Table("audit_entries", m,
            Column("idx", Integer, nullable=False),
            Column("workspace_id", Text, nullable=False, default=""),
            Column("event_type", Text, nullable=False),
            Column("agent_name", Text, nullable=False),
            Column("details", Text, nullable=False, default="{}"),
            Column("session_id", Text, nullable=False, default=""),
            Column("timestamp", Text, nullable=False),
            Column("hash", Text, nullable=False),
            Column("prev_hash", Text, nullable=False),
        )

        Table("memory_entries", m,
            Column("namespace", Text, nullable=False),
            Column("key", Text, nullable=False),
            Column("workspace_id", Text, nullable=False, default=""),
            Column("value", Text, nullable=False, default=""),
            Column("source_agent", Text, nullable=False, default=""),
            Column("tags", Text, nullable=False, default="[]"),
            Column("created_at", Float, nullable=False),
            Column("ttl_seconds", Float),
            Column("access_count", Integer, nullable=False, default=0),
        )

        Table("compliance_reports", m,
            Column("id", Text, primary_key=True),
            Column("workspace_id", Text, nullable=False, default=""),
            Column("report_type", Text, nullable=False, default=""),
            Column("framework", Text, nullable=False, default=""),
            Column("compliance_score", Float, nullable=False, default=0),
            Column("data", Text, nullable=False, default="{}"),
        )

        Table("recovery_ledger", m,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("workspace_id", Text, nullable=False, default=""),
            Column("agent_name", Text, nullable=False),
            Column("incident_type", Text, nullable=False),
            Column("error_message", Text, nullable=False, default=""),
            Column("recovery_action", Text, nullable=False, default=""),
            Column("diagnosed_by", Text, nullable=False, default="rule"),
            Column("success", Integer, nullable=False, default=0),
            Column("confidence", Float, nullable=False, default=0.0),
            Column("evidence", Text, nullable=False, default="{}"),
            Column("timestamp", Text, nullable=False),
        )
        Index("idx_rl_agent", "agent_name", "workspace_id")
        Index("idx_rl_type", "incident_type")

        Table("recovery_rules", m,
            Column("rule_id", Text, primary_key=True),
            Column("workspace_id", Text, nullable=False, default=""),
            Column("name", Text, nullable=False),
            Column("incident_type", Text, nullable=False),
            Column("pattern", Text, nullable=False, default=""),
            Column("recovery_action", Text, nullable=False),
            Column("priority", Integer, nullable=False, default=50),
            Column("cooldown_seconds", Integer, nullable=False, default=300),
            Column("enabled", Integer, nullable=False, default=1),
        )

        Table("agent_checkpoints", m,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("workspace_id", Text, nullable=False, default=""),
            Column("agent_name", Text, nullable=False),
            Column("session_id", Text, nullable=False, default=""),
            Column("state_json", Text, nullable=False),
            Column("step", Text, nullable=False, default=""),
            Column("created_at", Text, nullable=False),
        )
        Index("idx_cp_agent_sess", "agent_name", "session_id", "workspace_id")

    def _w(self, ws: str) -> str:
        return ws or ""

    def _exec(self, sql: str, params: dict | None = None):
        with self._engine.begin() as conn:
            conn.execute(text(sql), params or {})

    def _fetchone(self, sql: str, params: dict | None = None) -> dict | None:
        with self._engine.connect() as conn:
            row = conn.execute(text(sql), params or {}).mappings().fetchone()
            return dict(row) if row else None

    def _fetchall(self, sql: str, params: dict | None = None) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(text(sql), params or {}).mappings().fetchall()
            return [dict(r) for r in rows]

    # ── Health ──────────────────────────────────────────────
    def heartbeat_upsert(self, agent_name: str, status: str, latency_ms: float,
                          timestamp: str, workspace_id: str = "") -> None:
        self._exec("""
            INSERT INTO health_heartbeats (agent_name, workspace_id, status, latency_ms, timestamp)
            VALUES (:agent, :ws, :status, :lat, :ts)
            ON CONFLICT (agent_name, workspace_id) DO UPDATE SET
                status = EXCLUDED.status, latency_ms = EXCLUDED.latency_ms, timestamp = EXCLUDED.timestamp
        """, {"agent": agent_name, "ws": self._w(workspace_id), "status": status, "lat": latency_ms, "ts": timestamp})

    def heartbeat_get(self, agent_name: str, workspace_id: str = "") -> dict | None:
        return self._fetchone("""
            SELECT * FROM health_heartbeats WHERE agent_name=:agent AND workspace_id=:ws
        """, {"agent": agent_name, "ws": self._w(workspace_id)})

    def heartbeat_all(self, workspace_id: str = "") -> list[dict]:
        return self._fetchall("""
            SELECT * FROM health_heartbeats WHERE workspace_id=:ws
        """, {"ws": self._w(workspace_id)})

    def heartbeat_delete(self, agent_name: str, workspace_id: str = "") -> None:
        self._exec("""
            DELETE FROM health_heartbeats WHERE agent_name=:agent AND workspace_id=:ws
        """, {"agent": agent_name, "ws": self._w(workspace_id)})

    def call_insert(self, agent_name: str, success: bool, latency_ms: float,
                     session_id: str, timestamp: str, workspace_id: str = "") -> int:
        with self._engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO health_calls (agent_name, workspace_id, success, latency_ms, session_id, timestamp)
                VALUES (:agent, :ws, :ok, :lat, :sid, :ts)
            """), {"agent": agent_name, "ws": self._w(workspace_id), "ok": 1 if success else 0,
                   "lat": latency_ms, "sid": session_id, "ts": timestamp})
            return result.lastrowid or 0

    def calls_by_agent(self, agent_name: str, limit: int = 500, workspace_id: str = "") -> list[dict]:
        return self._fetchall("""
            SELECT * FROM health_calls WHERE agent_name=:agent AND workspace_id=:ws
            ORDER BY timestamp DESC LIMIT :lim
        """, {"agent": agent_name, "ws": self._w(workspace_id), "lim": limit})

    def calls_count_by_agent(self, agent_name: str, workspace_id: str = "") -> int:
        r = self._fetchone("""
            SELECT COUNT(*) as cnt FROM health_calls WHERE agent_name=:agent AND workspace_id=:ws
        """, {"agent": agent_name, "ws": self._w(workspace_id)})
        return r["cnt"] if r else 0

    def calls_success_count(self, agent_name: str, workspace_id: str = "") -> int:
        r = self._fetchone("""
            SELECT COUNT(*) as cnt FROM health_calls WHERE agent_name=:agent AND workspace_id=:ws AND success=1
        """, {"agent": agent_name, "ws": self._w(workspace_id)})
        return r["cnt"] if r else 0

    def calls_latencies(self, agent_name: str, limit: int = 500, workspace_id: str = "") -> list[float]:
        rows = self._fetchall("""
            SELECT latency_ms FROM health_calls WHERE agent_name=:agent AND workspace_id=:ws
            ORDER BY timestamp DESC LIMIT :lim
        """, {"agent": agent_name, "ws": self._w(workspace_id), "lim": limit})
        return [r["latency_ms"] for r in rows]

    def calls_all_agents(self, workspace_id: str = "") -> list[str]:
        rows = self._fetchall("""
            SELECT DISTINCT agent_name FROM health_calls WHERE workspace_id=:ws
        """, {"ws": self._w(workspace_id)})
        return [r["agent_name"] for r in rows]

    # ── Cost ────────────────────────────────────────────────
    def cost_insert(self, agent_name: str, model: str, tokens_in: int, tokens_out: int,
                    cost_usd: float, session_id: str, timestamp: str,
                    workspace_id: str = "") -> int:
        with self._engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO cost_entries (agent_name, workspace_id, model, tokens_in, tokens_out, cost_usd, session_id, timestamp)
                VALUES (:agent, :ws, :model, :tin, :tout, :cost, :sid, :ts)
            """), {"agent": agent_name, "ws": self._w(workspace_id), "model": model,
                   "tin": tokens_in, "tout": tokens_out, "cost": cost_usd, "sid": session_id, "ts": timestamp})
            return result.lastrowid or 0

    def cost_all(self, workspace_id: str = "") -> list[dict]:
        return self._fetchall("""
            SELECT * FROM cost_entries WHERE workspace_id=:ws ORDER BY timestamp DESC
        """, {"ws": self._w(workspace_id)})

    def cost_by_agent(self, agent_name: str, workspace_id: str = "") -> list[dict]:
        return self._fetchall("""
            SELECT * FROM cost_entries WHERE agent_name=:agent AND workspace_id=:ws ORDER BY timestamp DESC
        """, {"agent": agent_name, "ws": self._w(workspace_id)})

    def cost_total_usd(self, workspace_id: str = "") -> float:
        r = self._fetchone("""
            SELECT COALESCE(SUM(cost_usd), 0) AS total FROM cost_entries WHERE workspace_id=:ws
        """, {"ws": self._w(workspace_id)})
        return r["total"] if r else 0.0

    def cost_token_totals(self, workspace_id: str = "") -> dict:
        r = self._fetchone("""
            SELECT COALESCE(SUM(tokens_in),0) as tokens_in, COALESCE(SUM(tokens_out),0) as tokens_out
            FROM cost_entries WHERE workspace_id=:ws
        """, {"ws": self._w(workspace_id)})
        if r:
            return {"tokens_in": r["tokens_in"], "tokens_out": r["tokens_out"],
                    "tokens_total": r["tokens_in"] + r["tokens_out"]}
        return {"tokens_in": 0, "tokens_out": 0, "tokens_total": 0}

    def budget_get(self, workspace_id: str = "") -> dict | None:
        return self._fetchone("""
            SELECT * FROM cost_budget WHERE workspace_id=:ws
        """, {"ws": self._w(workspace_id)})

    def budget_upsert(self, limit_usd: float, period: str, current_usd: float,
                       alert_threshold: float, auto_block: bool, workspace_id: str = "") -> None:
        self._exec("""
            INSERT INTO cost_budget (workspace_id, limit_usd, period, current_usd, alert_threshold, auto_block)
            VALUES (:ws, :lim, :per, :cur, :thr, :blk)
            ON CONFLICT (workspace_id) DO UPDATE SET
                limit_usd = EXCLUDED.limit_usd, period = EXCLUDED.period,
                alert_threshold = EXCLUDED.alert_threshold, auto_block = EXCLUDED.auto_block
        """, {"ws": self._w(workspace_id), "lim": limit_usd, "per": period, "cur": current_usd,
               "thr": alert_threshold, "blk": 1 if auto_block else 0})

    def budget_update_current(self, amount_usd: float, workspace_id: str = "") -> None:
        self._exec("""
            UPDATE cost_budget SET current_usd = current_usd + :amt WHERE workspace_id=:ws
        """, {"amt": amount_usd, "ws": self._w(workspace_id)})

    # ── Conflicts ───────────────────────────────────────────
    def conflict_insert(self, conflict_type: str, severity: str, agents_involved: str,
                        description: str, evidence: str, suggestion: str, detected_at: str,
                        workspace_id: str = "") -> int:
        with self._engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO conflicts (workspace_id, conflict_type, severity, agents_involved, description, evidence, suggestion, detected_at)
                VALUES (:ws, :ct, :sv, :ai, :desc, :ev, :sug, :ts)
            """), {"ws": self._w(workspace_id), "ct": conflict_type, "sv": severity,
                   "ai": agents_involved, "desc": description, "ev": evidence, "sug": suggestion, "ts": detected_at})
            return result.lastrowid or 0

    def conflicts_all(self, workspace_id: str = "") -> list[dict]:
        return self._fetchall("""
            SELECT * FROM conflicts WHERE workspace_id=:ws ORDER BY detected_at DESC
        """, {"ws": self._w(workspace_id)})

    def conflicts_count(self, workspace_id: str = "") -> int:
        r = self._fetchone("""
            SELECT COUNT(*) as cnt FROM conflicts WHERE workspace_id=:ws
        """, {"ws": self._w(workspace_id)})
        return r["cnt"] if r else 0

    # ── RBAC ────────────────────────────────────────────────
    def workspace_insert(self, ws_id: str, name: str, owner_user_id: str, created_at: str) -> None:
        self._exec("""
            INSERT INTO rbac_workspaces (workspace_id, name, owner_user_id, created_at) VALUES (:id, :nm, :own, :ts)
        """, {"id": ws_id, "nm": name, "own": owner_user_id, "ts": created_at})

    def workspace_get(self, ws_id: str) -> dict | None:
        return self._fetchone("""
            SELECT * FROM rbac_workspaces WHERE workspace_id=:id OR name=:id
        """, {"id": ws_id})

    def workspace_all(self) -> list[dict]:
        return self._fetchall("SELECT * FROM rbac_workspaces")

    def rbac_user_insert(self, user_id: str, workspace_id: str, role: str, created_at: str) -> None:
        self._exec("""
            INSERT INTO rbac_users (user_id, workspace_id, role, created_at) VALUES (:uid, :ws, :r, :ts)
        """, {"uid": user_id, "ws": workspace_id, "r": role, "ts": created_at})

    def apikey_insert(self, key_id: str, key_hash: str, name: str, role: str,
                       workspace_id: str, created_at: str, expires_at: str | None) -> None:
        self._exec("""
            INSERT INTO rbac_api_keys (key_id, key_hash, name, role, workspace_id, created_at, expires_at)
            VALUES (:kid, :kh, :nm, :r, :ws, :ts, :exp)
        """, {"kid": key_id, "kh": key_hash, "nm": name, "r": role, "ws": workspace_id,
               "ts": created_at, "exp": expires_at})

    def apikey_get_by_hash(self, key_hash: str) -> dict | None:
        return self._fetchone("""
            SELECT * FROM rbac_api_keys WHERE key_hash=:kh
        """, {"kh": key_hash})

    # ── Registered Agents ───────────────────────────────────
    def agent_register(self, agent_id: str, workspace_id: str, agent_name: str,
                        model: str, upstream_url: str, created_at: str,
                        framework: str = "", version: str = "", description: str = "",
                        capabilities: str = "{}", registry_config: str = "{}",
                        governance_config: str = "{}", config_path: str = "") -> None:
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
        self._exec("""
            INSERT INTO registered_agents (
                agent_id, workspace_id, agent_name, framework, version, description,
                model, upstream_url, capabilities, registry_config, governance_config,
                tags, config_path, status, last_heartbeat, pid, created_at
            )
            VALUES (
                :id, :ws, :nm, :fw, :ver, :desc, :md, :url, :caps, :reg, :gov,
                '[]', :path, 'registered', '', 0, :ts
            )
            ON CONFLICT (agent_id) DO UPDATE SET
                workspace_id = EXCLUDED.workspace_id,
                agent_name = EXCLUDED.agent_name,
                framework = EXCLUDED.framework,
                version = EXCLUDED.version,
                description = EXCLUDED.description,
                model = EXCLUDED.model,
                upstream_url = EXCLUDED.upstream_url,
                capabilities = EXCLUDED.capabilities,
                registry_config = EXCLUDED.registry_config,
                governance_config = EXCLUDED.governance_config,
                config_path = EXCLUDED.config_path,
                status = EXCLUDED.status,
                created_at = EXCLUDED.created_at
        """, {
            "id": agent_id, "ws": workspace_id, "nm": agent_name,
            "fw": framework, "ver": version, "desc": description,
            "md": model, "url": upstream_url, "caps": capabilities,
            "reg": registry_config, "gov": governance_config,
            "path": config_path, "ts": created_at,
        })

    def agent_get(self, agent_id: str) -> dict | None:
        return self._fetchone("""
            SELECT * FROM registered_agents WHERE agent_id=:id
        """, {"id": agent_id})

    def agent_list(self, workspace_id: str = "") -> list[dict]:
        return self._fetchall("""
            SELECT * FROM registered_agents WHERE workspace_id=:ws
            ORDER BY framework, agent_name
        """, {"ws": workspace_id})

    def agent_list_by_status(self, workspace_id: str = "", status: str = "") -> list[dict]:
        if status:
            return self._fetchall("""
                SELECT * FROM registered_agents WHERE workspace_id=:ws AND status=:status
                ORDER BY framework, agent_name
            """, {"ws": workspace_id, "status": status})
        return self.agent_list(workspace_id)

    def agent_update_status(self, agent_id: str, status: str, pid: int = 0) -> bool:
        from datetime import datetime, timezone
        with self._engine.begin() as conn:
            result = conn.execute(text("""
                UPDATE registered_agents
                SET status=:status, pid=:pid, last_heartbeat=:ts
                WHERE agent_id=:id
            """), {
                "status": status, "pid": pid,
                "ts": datetime.now(timezone.utc).isoformat(), "id": agent_id,
            })
            return result.rowcount > 0

    def agent_heartbeat(self, agent_id: str) -> bool:
        from datetime import datetime, timezone
        with self._engine.begin() as conn:
            result = conn.execute(text("""
                UPDATE registered_agents SET last_heartbeat=:ts WHERE agent_id=:id
            """), {"ts": datetime.now(timezone.utc).isoformat(), "id": agent_id})
            return result.rowcount > 0

    def agent_list_stale(self, workspace_id: str = "",
                         max_age_seconds: int = 120) -> list[dict]:
        from datetime import datetime, timezone, timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)).isoformat()
        return self._fetchall("""
            SELECT * FROM registered_agents
            WHERE workspace_id=:ws AND status='running' AND last_heartbeat < :cutoff
        """, {"ws": workspace_id, "cutoff": cutoff})

    def agent_delete(self, agent_id: str) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(text("DELETE FROM registered_agents WHERE agent_id=:id"), {"id": agent_id})
            return result.rowcount > 0

    # ── Audit ───────────────────────────────────────────────
    def audit_insert(self, idx: int, event_type: str, agent_name: str, details: str,
                     session_id: str, timestamp: str, hash_val: str, prev_hash: str,
                     workspace_id: str = "") -> None:
        self._exec("""
            INSERT INTO audit_entries (idx, workspace_id, event_type, agent_name, details, session_id, timestamp, hash, prev_hash)
            VALUES (:ix, :ws, :et, :an, :dt, :sid, :ts, :h, :ph)
        """, {"ix": idx, "ws": self._w(workspace_id), "et": event_type, "an": agent_name,
               "dt": details, "sid": session_id, "ts": timestamp, "h": hash_val, "ph": prev_hash})

    def audit_all(self, workspace_id: str = "") -> list[dict]:
        return self._fetchall("""
            SELECT * FROM audit_entries WHERE workspace_id=:ws ORDER BY idx ASC
        """, {"ws": self._w(workspace_id)})

    def audit_count(self, workspace_id: str = "") -> int:
        r = self._fetchone("""
            SELECT COUNT(*) as cnt FROM audit_entries WHERE workspace_id=:ws
        """, {"ws": self._w(workspace_id)})
        return r["cnt"] if r else 0

    # ── Memory ──────────────────────────────────────────────
    def memory_upsert(self, namespace: str, key: str, value: str, source_agent: str,
                       tags: str, created_at: float, ttl_seconds: float | None,
                       workspace_id: str = "") -> None:
        self._exec("""
            INSERT INTO memory_entries (namespace, key, workspace_id, value, source_agent, tags, created_at, ttl_seconds)
            VALUES (:ns, :k, :ws, :v, :sa, :tg, :ca, :ttl)
            ON CONFLICT (namespace, key, workspace_id) DO UPDATE SET
                value = EXCLUDED.value, source_agent = EXCLUDED.source_agent, tags = EXCLUDED.tags,
                created_at = EXCLUDED.created_at, ttl_seconds = EXCLUDED.ttl_seconds, access_count = 0
        """, {"ns": namespace, "k": key, "ws": self._w(workspace_id), "v": value,
               "sa": source_agent, "tg": tags, "ca": created_at, "ttl": ttl_seconds})

    def memory_get(self, namespace: str, key: str, workspace_id: str = "") -> dict | None:
        return self._fetchone("""
            SELECT * FROM memory_entries WHERE namespace=:ns AND key=:k AND workspace_id=:ws
        """, {"ns": namespace, "k": key, "ws": self._w(workspace_id)})

    # ── Compliance Reports ─────────────────────────────────
    def compliance_report_insert(self, report_id: str, workspace_id: str,
                                  report_type: str, framework: str,
                                  score: float, data: str) -> None:
        self._exec("""
            INSERT INTO compliance_reports (id, workspace_id, report_type, framework, compliance_score, data)
            VALUES (:id, :ws, :rt, :fw, :sc, :dt)
            ON CONFLICT (id) DO UPDATE SET
                report_type=EXCLUDED.report_type, framework=EXCLUDED.framework,
                compliance_score=EXCLUDED.compliance_score, data=EXCLUDED.data
        """, {"id": report_id, "ws": self._w(workspace_id), "rt": report_type,
               "fw": framework, "sc": score, "dt": data})

    def compliance_report_get(self, report_id: str, workspace_id: str = "") -> dict | None:
        return self._fetchone("""
            SELECT * FROM compliance_reports WHERE id=:id AND workspace_id=:ws
        """, {"id": report_id, "ws": self._w(workspace_id)})

    def compliance_report_latest(self, report_type: str, workspace_id: str = "") -> dict | None:
        return self._fetchone("""
            SELECT * FROM compliance_reports WHERE report_type=:rt AND workspace_id=:ws
            ORDER BY compliance_score DESC LIMIT 1
        """, {"rt": report_type, "ws": self._w(workspace_id)})

    def compliance_reports_all(self, workspace_id: str = "") -> list[dict]:
        return self._fetchall("""
            SELECT * FROM compliance_reports WHERE workspace_id=:ws ORDER BY compliance_score DESC
        """, {"ws": self._w(workspace_id)})

    def recovery_ledger_insert(self, agent_name: str, incident_type: str,
                               error_message: str, recovery_action: str,
                               diagnosed_by: str, success: bool, confidence: float,
                               evidence: str, timestamp: str, workspace_id: str = "") -> int:
        with self._engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO recovery_ledger (workspace_id, agent_name, incident_type,
                    error_message, recovery_action, diagnosed_by, success, confidence,
                    evidence, timestamp)
                VALUES (:ws, :agent, :itype, :err, :action, :diagnosed_by,
                    :success, :confidence, :evidence, :ts)
                RETURNING id
            """), {
                "ws": self._w(workspace_id),
                "agent": agent_name,
                "itype": incident_type,
                "err": error_message,
                "action": recovery_action,
                "diagnosed_by": diagnosed_by,
                "success": 1 if success else 0,
                "confidence": confidence,
                "evidence": evidence,
                "ts": timestamp,
            })
            return int(result.scalar_one())

    def recovery_ledger_list(self, agent_name: str = "", incident_type: str = "",
                             workspace_id: str = "", limit: int = 100) -> list[dict]:
        conditions = ["workspace_id=:ws"]
        params: dict[str, Any] = {"ws": self._w(workspace_id), "lim": limit}
        if agent_name:
            conditions.append("agent_name=:agent")
            params["agent"] = agent_name
        if incident_type:
            conditions.append("incident_type=:itype")
            params["itype"] = incident_type
        where = " AND ".join(conditions)
        return self._fetchall(f"""
            SELECT * FROM recovery_ledger WHERE {where}
            ORDER BY timestamp DESC LIMIT :lim
        """, params)

    def recovery_ledger_similar(self, incident_type: str, error_message: str,
                                workspace_id: str = "", limit: int = 5) -> list[dict]:
        return self._fetchall("""
            SELECT * FROM recovery_ledger
            WHERE workspace_id=:ws AND incident_type=:itype AND success=1
            ORDER BY timestamp DESC LIMIT :lim
        """, {"ws": self._w(workspace_id), "itype": incident_type, "lim": limit})

    def recovery_rules_list(self, workspace_id: str = "") -> list[dict]:
        return self._fetchall("""
            SELECT * FROM recovery_rules WHERE workspace_id=:ws ORDER BY priority
        """, {"ws": self._w(workspace_id)})

    def recovery_rules_upsert(self, rule_id: str, name: str, incident_type: str,
                              pattern: str, recovery_action: str, priority: int,
                              cooldown_seconds: int, enabled: bool,
                              workspace_id: str = "") -> None:
        self._exec("""
            INSERT INTO recovery_rules (rule_id, workspace_id, name, incident_type,
                pattern, recovery_action, priority, cooldown_seconds, enabled)
            VALUES (:rid, :ws, :name, :itype, :pattern, :action, :priority,
                :cooldown, :enabled)
            ON CONFLICT (rule_id) DO UPDATE SET
                workspace_id = EXCLUDED.workspace_id,
                name = EXCLUDED.name,
                incident_type = EXCLUDED.incident_type,
                pattern = EXCLUDED.pattern,
                recovery_action = EXCLUDED.recovery_action,
                priority = EXCLUDED.priority,
                cooldown_seconds = EXCLUDED.cooldown_seconds,
                enabled = EXCLUDED.enabled
        """, {
            "rid": rule_id,
            "ws": self._w(workspace_id),
            "name": name,
            "itype": incident_type,
            "pattern": pattern,
            "action": recovery_action,
            "priority": priority,
            "cooldown": cooldown_seconds,
            "enabled": 1 if enabled else 0,
        })

    def checkpoint_insert(self, agent_name: str, session_id: str,
                          state_json: str, step: str, created_at: str,
                          workspace_id: str = "") -> int:
        with self._engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO agent_checkpoints (workspace_id, agent_name, session_id, state_json, step, created_at)
                VALUES (:ws, :agent, :sid, :state, :step, :ts)
                RETURNING id
            """), {
                "ws": self._w(workspace_id),
                "agent": agent_name,
                "sid": session_id,
                "state": state_json,
                "step": step,
                "ts": created_at,
            })
            return int(result.scalar_one())

    def checkpoint_latest(self, agent_name: str, session_id: str = "",
                          workspace_id: str = "") -> dict | None:
        params: dict[str, Any] = {"agent": agent_name, "ws": self._w(workspace_id)}
        session_filter = ""
        if session_id:
            session_filter = "AND session_id=:sid"
            params["sid"] = session_id
        return self._fetchone(f"""
            SELECT * FROM agent_checkpoints
            WHERE agent_name=:agent AND workspace_id=:ws {session_filter}
            ORDER BY created_at DESC LIMIT 1
        """, params)

    def checkpoint_list(self, agent_name: str = "", session_id: str = "",
                        workspace_id: str = "", limit: int = 50) -> list[dict]:
        conditions = ["workspace_id=:ws"]
        params: dict[str, Any] = {"ws": self._w(workspace_id), "lim": limit}
        if agent_name:
            conditions.append("agent_name=:agent")
            params["agent"] = agent_name
        if session_id:
            conditions.append("session_id=:sid")
            params["sid"] = session_id
        where = " AND ".join(conditions)
        return self._fetchall(f"""
            SELECT * FROM agent_checkpoints WHERE {where}
            ORDER BY created_at DESC LIMIT :lim
        """, params)

    def checkpoint_prune(self, max_age_days: int, workspace_id: str = "") -> int:
        from datetime import datetime, timezone, timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
        with self._engine.begin() as conn:
            result = conn.execute(text("""
                DELETE FROM agent_checkpoints WHERE workspace_id=:ws AND created_at < :cutoff
            """), {"ws": self._w(workspace_id), "cutoff": cutoff})
            return result.rowcount or 0

    # ── Lifecycle ───────────────────────────────────────────
    def clear_all(self) -> None:
        tables = [
            "health_heartbeats", "health_calls", "cost_entries", "cost_budget",
            "conflicts", "audit_entries", "rbac_api_keys", "rbac_users",
            "rbac_workspaces", "memory_entries", "registered_agents",
            "recovery_ledger", "recovery_rules",
            "agent_checkpoints",
        ]
        for t in tables:
            self._exec(f"DELETE FROM {t}")

    def close(self) -> None:
        if self._engine:
            self._engine.dispose()
