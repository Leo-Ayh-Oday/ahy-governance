"""LangChain Adapter 测试 — 用 mock callback 验证事件翻译正确"""

import pytest
from unittest.mock import MagicMock, patch

from ahy_governance.collector import GovernanceCollector, GovernancePipeline
from ahy_governance.events import (
    AgentStartEvent,
    AgentEndEvent,
    LLMCallEvent,
    LLMResultEvent,
    ToolStartEvent,
    ToolEndEvent,
    AgentErrorEvent,
)


def _langchain_available():
    try:
        from ahy_governance.adapters.langchain import _LANGCHAIN_AVAILABLE
        return _LANGCHAIN_AVAILABLE
    except ImportError:
        return False


def _make_handler(collector):
    """Create a LangChainGovernanceHandler, skipping if langchain unavailable."""
    if not _langchain_available():
        pytest.skip("langchain not installed")
    from ahy_governance.adapters.langchain import LangChainGovernanceHandler
    return LangChainGovernanceHandler(collector)


class TestAdapterRegistry:
    def test_list_adapters_includes_generic(self):
        from ahy_governance.adapters import list_adapters
        adapters = list_adapters()
        assert "generic" in adapters

    def test_get_adapter_returns_class(self):
        from ahy_governance.adapters import get_adapter
        cls = get_adapter("generic")
        assert cls is GovernancePipeline

    def test_get_adapter_unknown_returns_none(self):
        from ahy_governance.adapters import get_adapter
        assert get_adapter("nonexistent") is None

    def test_register_new_adapter(self):
        from ahy_governance.adapters import register_adapter, list_adapters, get_adapter

        class FakeCollector(GovernanceCollector):
            def on_agent_start(self, e): pass
            def on_agent_end(self, e): pass
            def on_llm_call(self, e): pass
            def on_llm_result(self, e): pass
            framework_name = "fake"

        register_adapter("fake_test", FakeCollector)
        assert "fake_test" in list_adapters()
        assert get_adapter("fake_test") is FakeCollector

    def test_register_overwrites_existing(self):
        from ahy_governance.adapters import register_adapter, get_adapter

        class CollectorV2(GovernanceCollector):
            def on_agent_start(self, e): pass
            def on_agent_end(self, e): pass
            def on_llm_call(self, e): pass
            def on_llm_result(self, e): pass
            framework_name = "v2"

        register_adapter("generic", CollectorV2)
        assert get_adapter("generic") is CollectorV2

        # Restore
        register_adapter("generic", GovernancePipeline)


@pytest.fixture
def mock_collector():
    """返回一个记录所有事件的 mock collector"""
    mc = MagicMock(spec=GovernanceCollector)
    mc.framework_name = "mock"
    return mc


@pytest.fixture
def langchain_handler(mock_collector):
    """导入 LangChain handler（如果 langchain 可用），否则用 mock"""
    try:
        from ahy_governance.adapters.langchain import LangChainGovernanceHandler
        return LangChainGovernanceHandler(mock_collector)
    except ImportError:
        pytest.skip("langchain not installed")


class TestLangChainHandlerAvailable:
    def test_handler_imports(self):
        from ahy_governance.adapters import list_adapters
        adapters = list_adapters()
        assert "generic" in adapters
        if _langchain_available():
            assert "langchain" in adapters


class TestAgentNameResolution:
    def test_resolve_by_name(self):
        from ahy_governance.adapters.langchain import LangChainGovernanceHandler
        name = LangChainGovernanceHandler._resolve_agent_name({"name": "MyAgent"})
        assert name == "MyAgent"

    def test_resolve_by_id_list(self):
        from ahy_governance.adapters.langchain import LangChainGovernanceHandler
        name = LangChainGovernanceHandler._resolve_agent_name(
            {"id": ["langchain", "AgentExecutor", "MyAgent"]}
        )
        assert name == "MyAgent"

    def test_resolve_fallback(self):
        from ahy_governance.adapters.langchain import LangChainGovernanceHandler
        name = LangChainGovernanceHandler._resolve_agent_name({})
        assert name == "agent"


class TestLangChainHandlerOnChainStart:
    def test_dispatches_agent_start(self, mock_collector):
        handler = _make_handler(mock_collector)
        handler.on_chain_start(
            {"name": "Planner"},
            {"task": "analyze"},
            run_id="run-1",
            parent_run_id="parent-1",
        )
        assert mock_collector.on_agent_start.called
        event = mock_collector.on_agent_start.call_args[0][0]
        assert event.agent_name == "Planner"
        assert event.input == {"task": "analyze"}
        assert event.session_id == "parent-1"

    def test_handles_non_dict_input(self, mock_collector):
        handler = _make_handler(mock_collector)
        handler.on_chain_start(
            {"name": "Agent"},
            "plain string input",
            run_id="run-2",
        )
        event = mock_collector.on_agent_start.call_args[0][0]
        assert event.input == {"input": "plain string input"}


class TestLangChainHandlerOnLLMEnd:
    def test_dispatches_llm_result(self, mock_collector):
        handler = _make_handler(mock_collector)
        handler.on_chain_start(
            {"name": "Planner"}, {"task": "x"},
            run_id="chain-1",
        )
        handler.on_llm_start(
            {"kwargs": {"model_name": "gpt-4o"}},
            ["prompt text"],
            run_id="llm-1",
            parent_run_id="chain-1",
        )
        mock_resp = MagicMock()
        mock_resp.model_name = "gpt-4o"
        mock_gen = MagicMock()
        mock_gen.text = "analysis result"
        mock_resp.generations = [[mock_gen]]
        mock_resp.llm_output = {
            "token_usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
        handler.on_llm_end(mock_resp, run_id="llm-1", parent_run_id="chain-1")
        assert mock_collector.on_llm_result.called
        event = mock_collector.on_llm_result.call_args[0][0]
        assert event.agent_name == "Planner"
        assert event.model == "gpt-4o"
        assert event.output == "analysis result"
        assert event.tokens_in == 100
        assert event.tokens_out == 50
        assert event.latency_ms >= 0


class TestLangChainHandlerOnToolEnd:
    def test_dispatches_tool_end(self, mock_collector):
        handler = _make_handler(mock_collector)
        handler.on_chain_start(
            {"name": "Planner"}, {"task": "x"},
            run_id="chain-1",
        )
        handler.on_tool_start(
            {"name": "search"}, "query text",
            run_id="tool-1", parent_run_id="chain-1",
        )
        handler.on_tool_end(
            "search results", run_id="tool-1",
            parent_run_id="chain-1", name="search",
        )
        assert mock_collector.on_tool_end.called
        event = mock_collector.on_tool_end.call_args[0][0]
        assert event.agent_name == "Planner"
        assert event.tool_name == "search"
        assert event.tool_output == "search results"


class TestLangChainHandlerOnChainError:
    def test_dispatches_error(self, mock_collector):
        handler = _make_handler(mock_collector)
        handler.on_chain_start(
            {"name": "Planner"}, {"task": "x"},
            run_id="chain-1",
        )
        handler.on_chain_error(
            ValueError("bad input"),
            run_id="chain-1",
        )
        assert mock_collector.on_error.called
        event = mock_collector.on_error.call_args[0][0]
        assert event.agent_name == "Planner"
        assert event.error_type == "ValueError"
        assert "bad input" in event.error_message


class TestLangChainHandlerOnToolError:
    def test_dispatches_failed_tool_end(self, mock_collector):
        handler = _make_handler(mock_collector)
        handler.on_chain_start(
            {"name": "Worker"}, {"task": "x"},
            run_id="chain-1",
        )
        handler.on_tool_start(
            {"name": "api_call"}, "request",
            run_id="tool-1", parent_run_id="chain-1",
        )
        handler.on_tool_error(
            ConnectionError("timeout"),
            run_id="tool-1", parent_run_id="chain-1", name="api_call",
        )
        event = mock_collector.on_tool_end.call_args[0][0]
        assert event.tool_name == "api_call"
        assert event.success is False


class TestLangChainHandlerNoAgentName:
    def test_chain_without_name_uses_id(self, mock_collector):
        handler = _make_handler(mock_collector)
        handler.on_chain_start(
            {"id": ["langchain", "AgentExecutor", "AutoAgent"]},
            {"input": "test"},
            run_id="run-1",
        )
        event = mock_collector.on_agent_start.call_args[0][0]
        assert event.agent_name == "AutoAgent"
