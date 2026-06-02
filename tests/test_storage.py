"""Tests for ahy_governance.storage — SQLite Database CRUD."""

import os
import tempfile
import pytest
from ahy_governance.storage import Database, create_database


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    return Database(path)


@pytest.fixture
def db_no_path():
    """Database with no path — disabled mode."""
    return Database("")


# ── Factory ─────────────────────────────────────────────────

class TestCreateDatabase:
    def test_sqlite_default(self, tmp_path):
        path = str(tmp_path / "factory.db")
        d = create_database(path)
        assert isinstance(d, Database)
        assert d.enabled

    def test_env_override(self, tmp_path, monkeypatch):
        path = str(tmp_path / "env.db")
        monkeypatch.setenv("AHY_DB_PATH", path)
        d = create_database()
        assert isinstance(d, Database)
        assert d.enabled

    def test_postgres_url_returns_pg(self, monkeypatch):
        # PostgresDatabase requires psycopg2; skip if not installed
        pytest.importorskip("psycopg2")
        from ahy_governance.storage_pg import PostgresDatabase

        def fake_init(self, url=None):
            self.url = url
            self.enabled = True

        monkeypatch.setattr(PostgresDatabase, "__init__", fake_init)
        d = create_database("postgresql://localhost/test")
        assert isinstance(d, PostgresDatabase)
        assert d.url == "postgresql://localhost/test"

    def test_postgres_recovery_schema_and_methods(self):
        sqlalchemy = pytest.importorskip("sqlalchemy")
        from ahy_governance.storage_pg import PostgresDatabase

        pg = object.__new__(PostgresDatabase)
        pg._metadata = sqlalchemy.MetaData()
        pg._define_tables()

        tables = pg._metadata.tables
        assert "recovery_ledger" in tables
        assert "recovery_rules" in tables
        assert "agent_checkpoints" in tables
        assert {"workspace_id", "agent_name", "incident_type", "recovery_action"}.issubset(
            tables["recovery_ledger"].columns.keys()
        )
        assert {"rule_id", "workspace_id", "pattern", "enabled"}.issubset(
            tables["recovery_rules"].columns.keys()
        )
        for method in (
            "recovery_ledger_insert",
            "recovery_ledger_list",
            "recovery_ledger_similar",
            "recovery_rules_list",
            "recovery_rules_upsert",
            "checkpoint_insert",
            "checkpoint_latest",
            "checkpoint_list",
            "checkpoint_prune",
        ):
            assert hasattr(PostgresDatabase, method)


# ── Disabled mode ───────────────────────────────────────────

class TestDisabledMode:
    def test_disabled_no_path(self):
        d = Database("")
        assert not d.enabled
        assert d._conn is None

    def test_disabled_enabled_flag(self):
        d = Database("")
        assert d.enabled is False
        d2 = Database(":memory:")
        assert d2.enabled is True


# ── Health ──────────────────────────────────────────────────

class TestHealth:
    def test_heartbeat_upsert_and_get(self, db):
        db.heartbeat_upsert("Planner", "ok", 150.0, "2026-01-01T00:00:00")
        row = db.heartbeat_get("Planner")
        assert row is not None
        assert row["agent_name"] == "Planner"
        assert row["status"] == "ok"
        assert row["latency_ms"] == 150.0

    def test_heartbeat_upsert_update(self, db):
        db.heartbeat_upsert("Planner", "ok", 100, "t1")
        db.heartbeat_upsert("Planner", "degraded", 200, "t2")
        row = db.heartbeat_get("Planner")
        assert row["status"] == "degraded"
        assert row["latency_ms"] == 200

    def test_heartbeat_all(self, db):
        db.heartbeat_upsert("A", "ok", 100, "t1")
        db.heartbeat_upsert("B", "ok", 200, "t2")
        rows = db.heartbeat_all()
        assert len(rows) == 2

    def test_heartbeat_delete(self, db):
        db.heartbeat_upsert("A", "ok", 100, "t1")
        db.heartbeat_delete("A")
        assert db.heartbeat_get("A") is None

    def test_heartbeat_workspace(self, db):
        db.heartbeat_upsert("A", "ok", 100, "t1", workspace_id="ws1")
        db.heartbeat_upsert("A", "degraded", 200, "t2", workspace_id="ws2")
        assert db.heartbeat_get("A", "ws1")["status"] == "ok"
        assert db.heartbeat_get("A", "ws2")["status"] == "degraded"

    def test_call_insert_and_query(self, db):
        db.call_insert("Planner", True, 100.0, "s1", "t1")
        db.call_insert("Planner", False, 200.0, "s1", "t2")
        calls = db.calls_by_agent("Planner")
        assert len(calls) == 2

    def test_calls_count(self, db):
        db.call_insert("A", True, 100, "s1", "t1")
        db.call_insert("A", True, 200, "s1", "t2")
        db.call_insert("A", False, 300, "s1", "t3")
        assert db.calls_count_by_agent("A") == 3
        assert db.calls_success_count("A") == 2

    def test_calls_latencies(self, db):
        db.call_insert("A", True, 100, "s1", "t1")
        db.call_insert("A", True, 200, "s1", "t2")
        lats = db.calls_latencies("A")
        assert len(lats) == 2

    def test_calls_all_agents(self, db):
        db.call_insert("A", True, 100, "s1", "t1")
        db.call_insert("B", True, 200, "s1", "t2")
        agents = db.calls_all_agents()
        assert set(agents) == {"A", "B"}

    def test_calls_empty(self, db):
        assert db.calls_count_by_agent("X") == 0
        assert db.calls_success_count("X") == 0
        assert db.calls_latencies("X") == []
        assert db.calls_all_agents() == []


# ── Cost ────────────────────────────────────────────────────

class TestCost:
    def test_cost_insert_and_all(self, db):
        db.cost_insert("Planner", "gpt-4o", 100, 50, 0.05, "s1", "t1")
        db.cost_insert("Executor", "haiku", 200, 100, 0.01, "s1", "t2")
        all_entries = db.cost_all()
        assert len(all_entries) == 2

    def test_cost_by_agent(self, db):
        db.cost_insert("A", "gpt-4o", 100, 50, 0.05, "s1", "t1")
        db.cost_insert("B", "haiku", 200, 100, 0.01, "s1", "t2")
        a_entries = db.cost_by_agent("A")
        assert len(a_entries) == 1

    def test_cost_total(self, db):
        db.cost_insert("A", "m", 100, 50, 1.5, "s1", "t1")
        db.cost_insert("B", "m", 100, 50, 2.5, "s1", "t2")
        assert db.cost_total_usd() == 4.0

    def test_cost_total_empty(self, db):
        assert db.cost_total_usd() == 0.0

    def test_cost_token_totals(self, db):
        db.cost_insert("A", "m", 100, 50, 1.0, "s1", "t1")
        db.cost_insert("B", "m", 200, 80, 2.0, "s1", "t2")
        totals = db.cost_token_totals()
        assert totals["tokens_in"] == 300
        assert totals["tokens_out"] == 130
        assert totals["tokens_total"] == 430

    def test_cost_token_totals_empty(self, db):
        totals = db.cost_token_totals()
        assert totals["tokens_in"] == 0
        assert totals["tokens_out"] == 0

    def test_budget_upsert_and_get(self, db):
        db.budget_upsert(100.0, "monthly", 50.0, 0.8, True)
        b = db.budget_get()
        assert b is not None
        assert b["limit_usd"] == 100.0
        assert b["period"] == "monthly"

    def test_budget_update_current(self, db):
        db.budget_upsert(100.0, "monthly", 0, 0.8, True)
        db.budget_update_current(25.0)
        assert db.budget_get()["current_usd"] == 25.0
        db.budget_update_current(10.0)
        assert db.budget_get()["current_usd"] == 35.0

    def test_budget_none_when_empty(self, db):
        assert db.budget_get() is None


# ── Conflicts ───────────────────────────────────────────────

class TestConflicts:
    def test_conflict_insert_and_list(self, db):
        db.conflict_insert("fact", "HIGH", '["A","B"]', "desc", "{}", "fix", "t1")
        db.conflict_insert("dep", "LOW", '["C"]', "desc2", "{}", "fix2", "t2")
        all_conflicts = db.conflicts_all()
        assert len(all_conflicts) == 2

    def test_conflict_count(self, db):
        db.conflict_insert("fact", "HIGH", '["A"]', "d", "{}", "s", "t1")
        db.conflict_insert("dep", "LOW", '["B"]', "d", "{}", "s", "t2")
        assert db.conflicts_count() == 2

    def test_conflict_count_empty(self, db):
        assert db.conflicts_count() == 0


# ── RBAC ────────────────────────────────────────────────────

class TestRBAC:
    def test_workspace_insert_and_get(self, db):
        db.workspace_insert("ws1", "My WS", "owner1", "2026-01-01")
        ws = db.workspace_get("ws1")
        assert ws is not None
        assert ws["name"] == "My WS"

    def test_workspace_get_by_name(self, db):
        db.workspace_insert("ws1", "My WS", "owner1", "2026-01-01")
        ws = db.workspace_get("My WS")
        assert ws is not None
        assert ws["workspace_id"] == "ws1"

    def test_workspace_get_nonexistent(self, db):
        assert db.workspace_get("nope") is None

    def test_workspace_all(self, db):
        db.workspace_insert("ws1", "A", "o1", "t1")
        db.workspace_insert("ws2", "B", "o2", "t2")
        assert len(db.workspace_all()) == 2

    def test_rbac_user_insert(self, db):
        db.workspace_insert("ws1", "A", "o1", "t1")
        db.rbac_user_insert("user1", "ws1", "admin", "t1")
        # No direct get method, but workspace users are queried via API

    def test_apikey_insert_and_get(self, db):
        db.workspace_insert("ws1", "A", "o1", "t1")
        db.apikey_insert("kid", "hash123", "my-key", "admin", "ws1", "t1", None)
        row = db.apikey_get_by_hash("hash123")
        assert row is not None
        assert row["name"] == "my-key"

    def test_apikey_get_nonexistent(self, db):
        assert db.apikey_get_by_hash("nope") is None


# ── Registered Agents ───────────────────────────────────────

class TestRegisteredAgents:
    def test_agent_register_and_get(self, db):
        db.agent_register("a1", "ws1", "Planner", "gpt-4o", "http://localhost:8001", "t1")
        row = db.agent_get("a1")
        assert row is not None
        assert row["agent_name"] == "Planner"

    def test_agent_get_nonexistent(self, db):
        assert db.agent_get("nope") is None

    def test_agent_list(self, db):
        db.agent_register("a1", "ws1", "P", "m", "u", "t1")
        db.agent_register("a2", "ws1", "E", "m", "u", "t2")
        assert len(db.agent_list("ws1")) == 2

    def test_agent_delete(self, db):
        db.agent_register("a1", "ws1", "P", "m", "u", "t1")
        assert db.agent_delete("a1") is True
        assert db.agent_get("a1") is None

    def test_agent_delete_nonexistent(self, db):
        assert db.agent_delete("nope") is False


# ── Audit ───────────────────────────────────────────────────

class TestAudit:
    def test_audit_insert_and_all(self, db):
        db.audit_insert(1, "start", "Planner", "{}", "s1", "t1", "h1", "h0")
        db.audit_insert(2, "end", "Planner", "{}", "s1", "t2", "h2", "h1")
        rows = db.audit_all()
        assert len(rows) == 2
        assert rows[0]["idx"] == 1

    def test_audit_count(self, db):
        db.audit_insert(1, "x", "A", "{}", "s1", "t1", "h1", "h0")
        assert db.audit_count() == 1

    def test_audit_count_empty(self, db):
        assert db.audit_count() == 0


# ── Memory ──────────────────────────────────────────────────

class TestMemory:
    def test_memory_upsert_and_get(self, db):
        db.memory_upsert("ns1", "k1", "v1", "Agent1", "[]", 1000.0, None)
        row = db.memory_get("ns1", "k1")
        assert row is not None
        assert row["value"] == "v1"

    def test_memory_upsert_update(self, db):
        db.memory_upsert("ns1", "k1", "v1", "A1", "[]", 1000.0, None)
        db.memory_upsert("ns1", "k1", "v2", "A2", "[]", 2000.0, None)
        row = db.memory_get("ns1", "k1")
        assert row["value"] == "v2"
        assert row["source_agent"] == "A2"

    def test_memory_get_nonexistent(self, db):
        assert db.memory_get("ns", "nope") is None


# ── Compliance Reports ──────────────────────────────────────

class TestComplianceReports:
    def test_insert_and_get(self, db):
        db.compliance_report_insert("r1", "ws1", "soc2", "SOC2", 0.95, '{"ok":true}')
        row = db.compliance_report_get("r1", "ws1")
        assert row is not None
        assert row["framework"] == "SOC2"

    def test_get_nonexistent(self, db):
        assert db.compliance_report_get("nope") is None

    def test_latest(self, db):
        db.compliance_report_insert("r1", "ws1", "soc2", "SOC2", 0.9, '{}')
        db.compliance_report_insert("r2", "ws1", "soc2", "SOC2", 0.95, '{}')
        latest = db.compliance_report_latest("soc2", "ws1")
        assert latest["id"] == "r2"

    def test_all(self, db):
        db.compliance_report_insert("r1", "ws1", "t", "f", 0.9, '{}')
        db.compliance_report_insert("r2", "ws1", "t", "f", 0.8, '{}')
        assert len(db.compliance_reports_all("ws1")) == 2


# ── Anomalies ───────────────────────────────────────────────

class TestAnomalies:
    def test_insert_and_list(self, db):
        db.anomaly_insert("TOKEN_SPIKE", "Planner", "HIGH", "spike", 1000, 100, 500, '{}', "t1")
        db.anomaly_insert("RATE_DROP", "Executor", "LOW", "drop", 0.5, 0.9, 0.2, '{}', "t2")
        rows = db.anomalies_list()
        assert len(rows) == 2

    def test_list_empty(self, db):
        assert db.anomalies_list() == []


# ── Cost Recommendations ────────────────────────────────────

class TestRecommendations:
    def test_insert_and_list(self, db):
        db.recommendation_insert("downgrade", "HIGH", "Planner", "use haiku",
                                  "gpt-4o", "haiku", 50.0, '{}', "t1")
        rows = db.recommendations_list()
        assert len(rows) == 1
        assert rows[0]["rec_type"] == "downgrade"

    def test_list_empty(self, db):
        assert db.recommendations_list() == []


class TestRecoveryStorage:
    def test_recovery_ledger_insert_list_and_similar(self, db):
        failed_id = db.recovery_ledger_insert(
            "Planner", "timeout", "slow call", "retry_same_agent",
            "rule", False, 0.8, '{"source":"test"}',
            "2026-06-02T00:00:00+00:00", workspace_id="ws1",
        )
        success_id = db.recovery_ledger_insert(
            "Planner", "timeout", "slow call", "retry_same_agent",
            "llm", True, 0.9, '{"source":"test"}',
            "2026-06-02T00:01:00+00:00", workspace_id="ws1",
        )
        db.recovery_ledger_insert(
            "Planner", "timeout", "other workspace", "alert_human",
            "rule", True, 0.4, "{}",
            "2026-06-02T00:02:00+00:00", workspace_id="ws2",
        )

        rows = db.recovery_ledger_list(
            agent_name="Planner", incident_type="timeout", workspace_id="ws1",
        )
        similar = db.recovery_ledger_similar("timeout", "slow call", workspace_id="ws1")

        assert failed_id > 0
        assert success_id > failed_id
        assert [row["id"] for row in rows] == [success_id, failed_id]
        assert len(similar) == 1
        assert similar[0]["id"] == success_id
        assert similar[0]["success"] == 1

    def test_recovery_rules_upsert_list_and_workspace_isolation(self, db):
        db.recovery_rules_upsert(
            "rule-1", "Retry timeout", "timeout", "timeout",
            "retry_same_agent", 20, 60, True, workspace_id="ws1",
        )
        db.recovery_rules_upsert(
            "rule-2", "Alert", "execution_error", "failed",
            "alert_human", 30, 120, False, workspace_id="ws2",
        )
        db.recovery_rules_upsert(
            "rule-1", "Retry timeout fast", "timeout", "timeout",
            "restart_agent", 10, 30, True, workspace_id="ws1",
        )

        ws1_rules = db.recovery_rules_list("ws1")
        ws2_rules = db.recovery_rules_list("ws2")

        assert len(ws1_rules) == 1
        assert ws1_rules[0]["rule_id"] == "rule-1"
        assert ws1_rules[0]["name"] == "Retry timeout fast"
        assert ws1_rules[0]["recovery_action"] == "restart_agent"
        assert ws1_rules[0]["priority"] == 10
        assert len(ws2_rules) == 1
        assert ws2_rules[0]["enabled"] == 0


# ── Lifecycle ───────────────────────────────────────────────

class TestCheckpoints:
    def test_insert_and_latest_by_session(self, db):
        first_id = db.checkpoint_insert(
            "Planner", "s1", '{"step": 1}', "step-1",
            "2026-06-02T00:00:00+00:00", workspace_id="ws1",
        )
        second_id = db.checkpoint_insert(
            "Planner", "s1", '{"step": 47}', "step-47",
            "2026-06-02T00:01:00+00:00", workspace_id="ws1",
        )
        latest = db.checkpoint_latest("Planner", "s1", "ws1")
        assert first_id > 0
        assert latest["id"] == second_id
        assert latest["state_json"] == '{"step": 47}'
        assert latest["step"] == "step-47"

    def test_checkpoint_workspace_isolation(self, db):
        db.checkpoint_insert("Planner", "s1", '{"ws": 1}', "a", "t1", "ws1")
        db.checkpoint_insert("Planner", "s1", '{"ws": 2}', "b", "t2", "ws2")
        assert db.checkpoint_latest("Planner", "s1", "ws1")["state_json"] == '{"ws": 1}'
        assert db.checkpoint_latest("Planner", "s1", "ws2")["state_json"] == '{"ws": 2}'

    def test_checkpoint_list_and_prune(self, db):
        db.checkpoint_insert("Planner", "s1", '{"old": true}', "old",
                             "2020-01-01T00:00:00+00:00", "ws1")
        db.checkpoint_insert("Planner", "s2", '{"new": true}', "new",
                             "2999-01-01T00:00:00+00:00", "ws1")
        rows = db.checkpoint_list(agent_name="Planner", workspace_id="ws1")
        assert len(rows) == 2
        assert db.checkpoint_prune(7, "ws1") == 1
        rows = db.checkpoint_list(agent_name="Planner", workspace_id="ws1")
        assert len(rows) == 1
        assert rows[0]["session_id"] == "s2"


class TestLifecycle:
    def test_clear_all(self, db):
        db.heartbeat_upsert("A", "ok", 100, "t1")
        db.cost_insert("A", "m", 100, 50, 1.0, "s1", "t1")
        db.conflict_insert("t", "H", '[]', "d", "{}", "s", "t1")
        db.audit_insert(1, "x", "A", "{}", "s1", "t1", "h1", "h0")
        db.memory_upsert("ns", "k", "v", "A", "[]", 1000, None)
        db.anomaly_insert("T", "A", "H", "d", 1, 0, 0, '{}', "t1")
        db.recommendation_insert("r", "H", "A", "d", "m1", "m2", 0, '{}', "t1")
        db.recovery_ledger_insert("A", "timeout", "d", "retry_same_agent",
                                  "rule", True, 0.9, "{}", "t1")
        db.recovery_rules_upsert("rule-1", "Retry", "timeout", "timeout",
                                 "retry_same_agent", 1, 60, True)
        db.checkpoint_insert("A", "s1", '{"step": 1}', "step-1", "t1")
        db.clear_all()
        assert db.heartbeat_all() == []
        assert db.cost_all() == []
        assert db.conflicts_all() == []
        assert db.audit_all() == []
        assert db.anomalies_list() == []
        assert db.recommendations_list() == []
        assert db.recovery_ledger_list() == []
        assert db.recovery_rules_list() == []
        assert db.checkpoint_list() == []

    def test_close(self, db):
        db.close()
        # After close, operations should fail — but we just test no crash on close
