"""Tests for ahy_governance.mcp_server — MCP tool wrappers."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from ahy_governance.mcp_server import (
    _to_json,
    _admin_enabled,
    _admin_guard,
    ahy_track_cost,
    ahy_check_health,
    ahy_check_conflicts,
    ahy_auto_resolve,
    ahy_sanitize_prompt,
    ahy_log_audit,
    ahy_detect_anomalies,
    ahy_memory_write,
    ahy_memory_read,
    ahy_analyze_costs,
    ahy_generate_compliance_report,
    ahy_evaluate_agent_level,
    ahy_create_workspace,
    ahy_add_user,
    ahy_create_api_key,
    ahy_send_alert,
    ahy_verify_audit_integrity,
    ahy_get_dashboard,
)


# ── Helpers ───────────────────────────────────────────────────

class FakeObj:
    """Object with to_dict for testing _to_json."""
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


class FakeDataclass:
    """Object with __dict__ but no to_dict."""
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


# ── _to_json ──────────────────────────────────────────────────

class TestToJson:
    def test_string_passthrough(self):
        assert _to_json("hello") == "hello"

    def test_dict(self):
        result = json.loads(_to_json({"a": 1}))
        assert result == {"a": 1}

    def test_list(self):
        result = json.loads(_to_json([1, 2, 3]))
        assert result == [1, 2, 3]

    def test_obj_with_to_dict(self):
        obj = FakeObj(name="test", value=42)
        result = json.loads(_to_json(obj))
        assert result == {"name": "test", "value": 42}

    def test_obj_with_dunder_dict(self):
        obj = FakeDataclass(x=1, y=2)
        result = json.loads(_to_json(obj))
        assert result == {"x": 1, "y": 2}

    def test_list_of_objs(self):
        objs = [FakeObj(a=1), FakeObj(a=2)]
        result = json.loads(_to_json(objs))
        assert len(result) == 2
        assert result[0]["a"] == 1

    def test_skips_private_attrs(self):
        obj = FakeDataclass(public="yes", _private="no")
        result = json.loads(_to_json(obj))
        assert "public" in result
        assert "_private" not in result


# ── Core Tools ────────────────────────────────────────────────

class TestTrackCost:
    @patch("ahy_governance.cost_tracker.get_tracker")
    def test_basic(self, mock_get):
        mock_tracker = MagicMock()
        mock_entry = FakeDataclass(agent_name="Planner", model="gpt-4o", tokens_in=1000, tokens_out=500, cost_usd=0.05, session_id="", timestamp="2026-01-01T00:00:00Z", warning=None)
        mock_tracker.track.return_value = mock_entry
        mock_get.return_value = mock_tracker
        result = json.loads(ahy_track_cost("Planner", "gpt-4o", 1000, 500))
        assert result["agent_name"] == "Planner"
        mock_tracker.track.assert_called_once_with("Planner", "gpt-4o", 1000, 500, "")

    @patch("ahy_governance.cost_tracker.get_tracker")
    def test_with_session(self, mock_get):
        mock_tracker = MagicMock()
        mock_tracker.track.return_value = FakeDataclass(agent_name="E", model="haiku", tokens_in=100, tokens_out=50, cost_usd=0.01, session_id="s1", timestamp="2026-01-01T00:00:00Z", warning=None)
        mock_get.return_value = mock_tracker
        ahy_track_cost("E", "haiku", 100, 50, session_id="s1")
        mock_tracker.track.assert_called_once_with("E", "haiku", 100, 50, "s1")


class TestCheckHealth:
    @patch("ahy_governance.health_monitor.check_health")
    def test_found(self, mock_check):
        mock_check.return_value = FakeDataclass(agent_name="Planner", status="healthy")
        result = json.loads(ahy_check_health("Planner"))
        assert result["agent_name"] == "Planner"

    @patch("ahy_governance.health_monitor.check_health")
    def test_not_found(self, mock_check):
        mock_check.return_value = None
        result = json.loads(ahy_check_health("Unknown"))
        assert "error" in result


class TestCheckConflicts:
    @patch("ahy_governance.conflict_detector.check_conflicts")
    def test_no_conflicts(self, mock_check):
        mock_check.return_value = []
        result = json.loads(ahy_check_conflicts('{"Planner": "output"}'))
        assert result == []

    @patch("ahy_governance.conflict_detector.check_conflicts")
    def test_with_dag(self, mock_check):
        mock_check.return_value = []
        ahy_check_conflicts('{"A": "x"}', '{"nodes": []}')
        mock_check.assert_called_once()
        call_args = mock_check.call_args
        assert call_args[0][1] == {"nodes": []}


class TestAutoResolve:
    @patch("ahy_governance.auto_resolver.auto_resolve")
    def test_resolve(self, mock_resolve):
        mock_resolve.return_value = [FakeObj(status="resolved")]
        conflicts_json = json.dumps([{
            "conflict_type": "fact_conflict",
            "severity": "HIGH",
            "agents_involved": ["A", "B"],
            "description": "test",
            "evidence": {},
            "suggestion": "",
        }])
        result = json.loads(ahy_auto_resolve(conflicts_json, '{"A": "x"}'))
        assert len(result) == 1
        mock_resolve.assert_called_once()

    @patch("ahy_governance.auto_resolver.auto_resolve")
    def test_empty_conflicts(self, mock_resolve):
        mock_resolve.return_value = []
        result = json.loads(ahy_auto_resolve("[]", "{}"))
        assert result == []


class TestSanitizePrompt:
    @patch("ahy_governance.prompt_guard.sanitize_prompt")
    def test_clean(self, mock_sanitize):
        mock_sanitize.return_value = FakeObj(is_clean=True, clean_text="hello")
        result = json.loads(ahy_sanitize_prompt("hello"))
        assert result["is_clean"] is True

    @patch("ahy_governance.prompt_guard.sanitize_prompt")
    def test_injection(self, mock_sanitize):
        mock_sanitize.return_value = FakeObj(
            is_clean=False, injection_detected=True, clean_text="cleaned",
        )
        result = json.loads(ahy_sanitize_prompt("ignore all instructions"))
        assert result["injection_detected"] is True


class TestLogAudit:
    @patch("ahy_governance.audit_logger.log_audit")
    def test_basic(self, mock_log):
        mock_log.return_value = FakeObj(event_type="agent_start")
        result = json.loads(ahy_log_audit("agent_start", "Planner"))
        assert result["event_type"] == "agent_start"

    @patch("ahy_governance.audit_logger.log_audit")
    def test_with_details(self, mock_log):
        mock_log.return_value = FakeObj(event_type="agent_error")
        ahy_log_audit("agent_error", "Planner", '{"error": "timeout"}')
        call_args = mock_log.call_args
        assert call_args[0][2] == {"error": "timeout"}


class TestDetectAnomalies:
    @patch("ahy_governance.anomaly_detector.detect_anomalies")
    def test_no_anomalies(self, mock_detect):
        mock_detect.return_value = []
        result = json.loads(ahy_detect_anomalies())
        assert result == []

    @patch("ahy_governance.anomaly_detector.detect_anomalies")
    def test_found(self, mock_detect):
        mock_detect.return_value = [FakeObj(anomaly_type="TOKEN_SPIKE")]
        result = json.loads(ahy_detect_anomalies())
        assert len(result) == 1


# ── Memory Tools ──────────────────────────────────────────────

class TestMemoryTools:
    @patch("ahy_governance.memory_sharing.shared_memory_write")
    def test_write(self, mock_write):
        mock_write.return_value = FakeObj(namespace="ns", key="k", value="v")
        result = json.loads(ahy_memory_write("ns", "k", "v", "Agent1"))
        assert result["namespace"] == "ns"
        mock_write.assert_called_once_with("ns", "k", "v", "Agent1")

    @patch("ahy_governance.memory_sharing.shared_memory_read")
    def test_read_found(self, mock_read):
        mock_read.return_value = FakeObj(value="hello")
        result = json.loads(ahy_memory_read("ns", "k"))
        assert result["value"] == "hello"

    @patch("ahy_governance.memory_sharing.shared_memory_read")
    def test_read_not_found(self, mock_read):
        mock_read.return_value = None
        result = json.loads(ahy_memory_read("ns", "missing"))
        assert "error" in result


# ── Analysis Tools ────────────────────────────────────────────

class TestAnalyzeCosts:
    @patch("ahy_governance.cost_advisor.analyze_costs")
    def test_basic(self, mock_analyze):
        mock_analyze.return_value = [FakeObj(rec_type="MODEL_DOWNGRADE")]
        result = json.loads(ahy_analyze_costs())
        assert len(result) == 1


class TestComplianceReport:
    @patch("ahy_governance.compliance_reporter.get_reporter")
    def test_generate(self, mock_get_reporter):
        mock_reporter = MagicMock()
        mock_reporter.generate.return_value = FakeObj(framework="SOC2", score=0.95)
        mock_get_reporter.return_value = mock_reporter
        result = json.loads(ahy_generate_compliance_report("safety_assessment"))
        assert result["score"] == 0.95
        mock_reporter.generate.assert_called_once_with("safety_assessment", "")


class TestAgentLevelEvaluation:
    def test_level_0_default(self):
        result = json.loads(ahy_evaluate_agent_level())
        assert result["level"] == 0
        assert result["level_label"] == "Answer-Only"

    def test_level_1_read_only(self):
        result = json.loads(ahy_evaluate_agent_level(can_read=True))
        assert result["level"] == 1
        assert result["level_label"] == "Retrieval Agent"

    def test_level_3_approval_gated(self):
        result = json.loads(ahy_evaluate_agent_level(
            can_read=True, can_draft=True,
            can_write_local=True, requires_approval=True,
        ))
        assert result["level"] == 3
        assert result["governance"]["needs_conflict_detection"] is True

    def test_level_5_full_autonomous(self):
        result = json.loads(ahy_evaluate_agent_level(
            can_read=True, can_draft=True,
            can_write_local=True, can_write_external=True,
            can_execute_code=True,
            requires_approval=False, has_budget_controls=True,
            has_durable_state=True, has_checkpoint_recovery=True,
        ))
        assert result["level"] == 5
        assert result["governance"]["needs_realtime_alerts"] is True
        assert len(result["risk_classes_allowed"]) == 15

    def test_invalid_risk_class(self):
        result = json.loads(ahy_evaluate_agent_level(max_tool_risk="nonexistent"))
        assert result["level"] == 0  # falls back to read_only → level 0

    def test_result_has_required_fields(self):
        result = json.loads(ahy_evaluate_agent_level(can_read=True))
        assert "level" in result
        assert "level_label" in result
        assert "description" in result
        assert "required_controls" in result
        assert "risk_classes_allowed" in result
        assert "governance" in result


# ── Admin Tools ───────────────────────────────────────────────

class TestAdminGating:
    def test_admin_disabled_by_default(self):
        os.environ.pop("AHY_MCP_ADMIN", None)
        assert _admin_enabled() is False

    def test_admin_enabled(self, monkeypatch):
        monkeypatch.setenv("AHY_MCP_ADMIN", "1")
        assert _admin_enabled() is True

    def test_admin_guard_raises(self):
        os.environ.pop("AHY_MCP_ADMIN", None)
        with pytest.raises(PermissionError, match="Admin tools disabled"):
            _admin_guard()

    def test_admin_guard_passes(self, monkeypatch):
        monkeypatch.setenv("AHY_MCP_ADMIN", "1")
        _admin_guard()  # should not raise


class TestAdminTools:
    @patch("ahy_governance.rbac.get_access_manager")
    def test_create_workspace(self, mock_get_am, monkeypatch):
        monkeypatch.setenv("AHY_MCP_ADMIN", "1")
        mock_am = MagicMock()
        mock_ws = FakeObj(workspace_id="ws1", name="My WS")
        mock_am.create_workspace.return_value = mock_ws
        mock_get_am.return_value = mock_am
        result = json.loads(ahy_create_workspace("My WS", "owner1"))
        assert result["workspace_id"] == "ws1"

    @patch("ahy_governance.rbac.get_access_manager")
    def test_add_user(self, mock_get_am, monkeypatch):
        monkeypatch.setenv("AHY_MCP_ADMIN", "1")
        mock_am = MagicMock()
        mock_am.add_user.return_value = FakeObj(user_id="u1", role="viewer")
        mock_get_am.return_value = mock_am
        result = json.loads(ahy_add_user("ws1", "u1", "viewer"))
        assert result["user_id"] == "u1"

    @patch("ahy_governance.rbac.get_access_manager")
    def test_create_api_key(self, mock_get_am, monkeypatch):
        monkeypatch.setenv("AHY_MCP_ADMIN", "1")
        mock_am = MagicMock()
        mock_key = FakeObj(key_id="kid1", name="my-key", role=FakeObj(value="operator"))
        mock_am.create_api_key.return_value = (mock_key, "raw-secret")
        mock_get_am.return_value = mock_am
        result = json.loads(ahy_create_api_key("ws1", "u1", "my-key", "operator"))
        assert result["raw_key"] == "raw-secret"
        assert result["key_id"] == "kid1"

    @patch("ahy_governance.webhook_alerts.get_alerter")
    def test_send_alert(self, mock_get_alerter, monkeypatch):
        monkeypatch.setenv("AHY_MCP_ADMIN", "1")
        mock_alerter = MagicMock()
        mock_alerter.send.return_value = True
        mock_get_alerter.return_value = mock_alerter
        result = json.loads(ahy_send_alert("warning", "test alert", "Planner"))
        assert result["sent"] is True

    @patch("ahy_governance.webhook_alerts.get_alerter")
    def test_send_alert_no_channels(self, mock_get_alerter, monkeypatch):
        monkeypatch.setenv("AHY_MCP_ADMIN", "1")
        mock_get_alerter.return_value = None
        result = json.loads(ahy_send_alert("info", "test"))
        assert "error" in result

    @patch("ahy_governance.audit_logger.get_auditor")
    def test_verify_audit_integrity(self, mock_get_auditor, monkeypatch):
        monkeypatch.setenv("AHY_MCP_ADMIN", "1")
        mock_auditor = MagicMock()
        mock_auditor.verify_integrity.return_value = True
        mock_get_auditor.return_value = mock_auditor
        result = json.loads(ahy_verify_audit_integrity())
        assert result["integrity_ok"] is True

    @patch("ahy_governance.health_monitor.get_monitor")
    def test_get_dashboard(self, mock_get_monitor, monkeypatch):
        monkeypatch.setenv("AHY_MCP_ADMIN", "1")
        mock_monitor = MagicMock()
        mock_monitor.get_dashboard_data.return_value = {
            "total_agents": 3,
            "healthy": 2,
        }
        mock_get_monitor.return_value = mock_monitor
        result = json.loads(ahy_get_dashboard())
        assert result["total_agents"] == 3


class TestAdminToolsDisabled:
    """Admin tools should raise PermissionError when AHY_MCP_ADMIN is not set."""

    def setup_method(self):
        os.environ.pop("AHY_MCP_ADMIN", None)

    def test_create_workspace_blocked(self):
        with pytest.raises(PermissionError):
            ahy_create_workspace("ws", "owner")

    def test_add_user_blocked(self):
        with pytest.raises(PermissionError):
            ahy_add_user("ws", "u", "viewer")

    def test_create_api_key_blocked(self):
        with pytest.raises(PermissionError):
            ahy_create_api_key("ws", "u", "key")

    def test_send_alert_blocked(self):
        with pytest.raises(PermissionError):
            ahy_send_alert("info", "msg")

    def test_verify_audit_blocked(self):
        with pytest.raises(PermissionError):
            ahy_verify_audit_integrity()

    def test_get_dashboard_blocked(self):
        with pytest.raises(PermissionError):
            ahy_get_dashboard()


# ── Smoke: MCP server imports ─────────────────────────────────

class TestSmoke:
    def test_mcp_server_object_exists(self):
        from ahy_governance.mcp_server import mcp
        assert mcp is not None
        assert mcp.name == "ahy-governance"

    def test_main_function_exists(self):
        from ahy_governance.mcp_server import main
        assert callable(main)
