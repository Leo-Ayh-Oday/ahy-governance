"""GovernancePipeline 单元测试 — 用 mock 验证事件正确路由到各治理模块"""

import pytest
from unittest.mock import patch, MagicMock

from ahy_governance.collector import GovernancePipeline, GovernanceCollector
from ahy_governance.events import (
    AgentStartEvent,
    AgentEndEvent,
    LLMCallEvent,
    LLMResultEvent,
    ToolStartEvent,
    ToolEndEvent,
    AgentErrorEvent,
)
from ahy_governance.audit_logger import AuditEventType


class TestGovernanceCollectorABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            GovernanceCollector()  # ABC with abstract methods

    def test_subclass_must_implement_abstract(self):
        with pytest.raises(TypeError):
            class Incomplete(GovernanceCollector):
                pass
            Incomplete()

    def test_valid_subclass(self):
        class Minimal(GovernanceCollector):
            def on_agent_start(self, e): pass
            def on_agent_end(self, e): pass
            def on_llm_call(self, e): pass
            def on_llm_result(self, e): pass

            @property
            def framework_name(self):
                return "test"

        m = Minimal()
        assert m.framework_name == "test"


class TestGovernancePipelineIdentity:
    def test_framework_name(self):
        p = GovernancePipeline()
        assert p.framework_name == "generic"

    def test_workspace_id(self):
        p = GovernancePipeline(workspace_id="ws-42")
        assert p.workspace_id == "ws-42"

    def test_default_workspace_id(self):
        p = GovernancePipeline()
        assert p.workspace_id == ""


class TestPipelineAgentStart:
    def test_routes_to_heartbeat_and_audit(self):
        p = GovernancePipeline(workspace_id="ws-1")
        event = AgentStartEvent(
            agent_name="Planner",
            model="gpt-4o",
            input={"task": "test"},
            session_id="s1",
        )

        with (
            patch("ahy_governance.health_monitor.get_monitor") as mock_mon,
            patch("ahy_governance.audit_logger.get_auditor") as mock_aud,
        ):
            p.on_agent_start(event)

        mock_mon.return_value.heartbeat.assert_called_once_with(
            "Planner", "ok", 0, "ws-1",
        )
        mock_aud.return_value.log.assert_called_once()
        call_args = mock_aud.return_value.log.call_args
        assert call_args[0][0] == AuditEventType.AGENT_START
        assert call_args[0][1] == "Planner"
        assert call_args[1]["workspace_id"] == "ws-1"


class TestPipelineAgentEnd:
    def test_routes_to_heartbeat_and_audit(self):
        p = GovernancePipeline(workspace_id="ws-1")
        event = AgentEndEvent(
            agent_name="Planner",
            output={"result": "ok"},
            total_latency_ms=5000,
            session_id="s1",
        )

        with (
            patch("ahy_governance.health_monitor.get_monitor") as mock_mon,
            patch("ahy_governance.audit_logger.get_auditor") as mock_aud,
        ):
            p.on_agent_end(event)

        mock_mon.return_value.heartbeat.assert_called_once_with(
            "Planner", "ok", 5000, "ws-1",
        )
        mock_aud.return_value.log.assert_called_once()
        call_args = mock_aud.return_value.log.call_args
        assert call_args[0][0] == AuditEventType.AGENT_COMPLETE

    def test_heartbeat_error_status_on_failure(self):
        p = GovernancePipeline()
        event = AgentEndEvent(agent_name="Worker", success=False)

        with (
            patch("ahy_governance.health_monitor.get_monitor") as mock_mon,
            patch("ahy_governance.audit_logger.get_auditor"),
        ):
            p.on_agent_end(event)

        mock_mon.return_value.heartbeat.assert_called_once_with(
            "Worker", "error", 0, "",
        )


class TestPipelineLLMResult:
    def test_routes_to_health_and_cost(self):
        p = GovernancePipeline(workspace_id="ws-1")
        event = LLMResultEvent(
            agent_name="Planner",
            model="claude-sonnet-4-6",
            output="analysis",
            tokens_in=1500,
            tokens_out=500,
            latency_ms=2300,
            session_id="s1",
        )

        with (
            patch("ahy_governance.health_monitor.get_monitor") as mock_mon,
            patch("ahy_governance.cost_tracker.get_tracker") as mock_trk,
        ):
            p.on_llm_result(event)

        mock_mon.return_value.record_call.assert_called_once_with(
            "Planner", True, 2300, "s1", "ws-1",
        )
        mock_trk.return_value.track.assert_called_once_with(
            "Planner", "claude-sonnet-4-6", 1500, 500, "s1", "ws-1",
        )

    def test_skips_cost_when_no_tokens(self):
        p = GovernancePipeline()
        event = LLMResultEvent(
            agent_name="Planner", model="gpt-4o", output="ok",
            tokens_in=0, tokens_out=0,  # no token data
        )

        with (
            patch("ahy_governance.health_monitor.get_monitor"),
            patch("ahy_governance.cost_tracker.get_tracker") as mock_trk,
        ):
            p.on_llm_result(event)

        mock_trk.return_value.track.assert_not_called()

    def test_cost_tracker_keyerror_suppressed(self):
        p = GovernancePipeline()
        event = LLMResultEvent(
            agent_name="Planner", model="unknown-model-xyz",
            output="ok", tokens_in=100, tokens_out=50,
        )

        with (
            patch("ahy_governance.health_monitor.get_monitor"),
            patch("ahy_governance.cost_tracker.get_tracker") as mock_trk,
        ):
            mock_trk.return_value.track.side_effect = KeyError("no pricing")
            p.on_llm_result(event)  # should not raise

        mock_trk.return_value.track.assert_called_once()

    def test_records_failed_call(self):
        p = GovernancePipeline()
        event = LLMResultEvent(
            agent_name="Planner", model="gpt-4o", output="",
            success=False, latency_ms=5000,
        )

        with patch("ahy_governance.health_monitor.get_monitor") as mock_mon:
            p.on_llm_result(event)

        mock_mon.return_value.record_call.assert_called_once_with(
            "Planner", False, 5000, "", "",
        )


class TestPipelineLLMCall:
    def test_is_noop(self):
        p = GovernancePipeline()
        event = LLMCallEvent(
            agent_name="Planner", model="gpt-4o",
            messages=[{"content": "hi"}],
        )
        # should not raise
        p.on_llm_call(event)


class TestPipelineToolEnd:
    def test_routes_to_audit(self):
        p = GovernancePipeline(workspace_id="ws-1")
        event = ToolEndEvent(
            agent_name="Planner",
            tool_name="search",
            tool_output="results",
            latency_ms=150,
            session_id="s1",
        )

        with patch("ahy_governance.audit_logger.get_auditor") as mock_aud:
            p.on_tool_end(event)

        mock_aud.return_value.log.assert_called_once()
        call_args = mock_aud.return_value.log.call_args
        assert call_args[0][0] == AuditEventType.TOOL_CALL
        assert call_args[0][1] == "Planner"


class TestPipelineError:
    def test_routes_to_heartbeat_and_audit(self):
        p = GovernancePipeline(workspace_id="ws-1")
        event = AgentErrorEvent(
            agent_name="Worker",
            error_type="ConnectionError",
            error_message="timeout",
            session_id="s1",
        )

        with (
            patch("ahy_governance.health_monitor.get_monitor") as mock_mon,
            patch("ahy_governance.audit_logger.get_auditor") as mock_aud,
        ):
            p.on_error(event)

        mock_mon.return_value.heartbeat.assert_called_once_with(
            "Worker", "error", 0, "ws-1",
        )
        mock_aud.return_value.log.assert_called_once()
        call_args = mock_aud.return_value.log.call_args
        assert call_args[0][0] == AuditEventType.AGENT_ERROR


class TestPipelineOptionalHooks:
    def test_tool_start_is_noop_by_default(self):
        p = GovernancePipeline()
        p.on_tool_start(ToolStartEvent(agent_name="A", tool_name="t"))
        # should not raise

    def test_default_on_error_is_noop(self):
        """ABC default on_error should be a no-op."""
        class Minimal(GovernanceCollector):
            def on_agent_start(self, e): pass
            def on_agent_end(self, e): pass
            def on_llm_call(self, e): pass
            def on_llm_result(self, e): pass

            @property
            def framework_name(self):
                return "minimal"

        m = Minimal()
        m.on_error(AgentErrorEvent(agent_name="X", error_type="E", error_message="m"))
        # should not raise
