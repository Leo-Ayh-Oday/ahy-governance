"""Governance Events 测试 — 序列化、字段默认值、时间戳自动填充"""

import json

import pytest

from ahy_governance.events import (
    AgentStartEvent,
    AgentEndEvent,
    LLMCallEvent,
    LLMResultEvent,
    ToolStartEvent,
    ToolEndEvent,
    AgentErrorEvent,
)


class TestAgentStartEvent:
    def test_minimal_creation(self):
        e = AgentStartEvent(agent_name="Planner")
        assert e.agent_name == "Planner"
        assert e.agent_id == ""
        assert e.model == ""
        assert e.input == {}
        assert e.session_id == ""
        assert e.timestamp  # auto-filled

    def test_full_creation(self):
        e = AgentStartEvent(
            agent_name="Reviewer",
            agent_id="rev-1",
            model="claude-sonnet-4-6",
            input={"task": "review contract"},
            session_id="sess-001",
            timestamp="2026-05-14T10:00:00Z",
        )
        assert e.agent_id == "rev-1"
        assert e.model == "claude-sonnet-4-6"
        assert e.input == {"task": "review contract"}
        assert e.timestamp == "2026-05-14T10:00:00Z"

    def test_to_dict(self):
        e = AgentStartEvent(agent_name="Planner", session_id="s1")
        d = e.to_dict()
        assert d["agent_name"] == "Planner"
        assert d["session_id"] == "s1"
        assert "timestamp" in d

    def test_json_roundtrip(self):
        e = AgentStartEvent(
            agent_name="Planner",
            model="gpt-4o",
            input={"key": "value"},
            session_id="s1",
        )
        d = e.to_dict()
        raw = json.dumps(d)
        loaded = json.loads(raw)
        assert loaded["agent_name"] == "Planner"
        assert loaded["input"] == {"key": "value"}


class TestAgentEndEvent:
    def test_defaults(self):
        e = AgentEndEvent(agent_name="Planner")
        assert e.success is True
        assert e.total_latency_ms == 0
        assert e.output == {}

    def test_with_output(self):
        e = AgentEndEvent(
            agent_name="Planner",
            output={"result": "done"},
            total_latency_ms=5200,
            session_id="s1",
        )
        assert e.output == {"result": "done"}
        assert e.total_latency_ms == 5200

    def test_failure(self):
        e = AgentEndEvent(agent_name="Worker", success=False)
        assert e.success is False


class TestLLMCallEvent:
    def test_minimal(self):
        e = LLMCallEvent(
            agent_name="Planner",
            model="claude-sonnet-4-6",
            messages=[{"content": "Hello"}],
        )
        assert len(e.messages) == 1
        assert e.tokens_in == 0

    def test_multiple_messages(self):
        msgs = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "What is 2+2?"},
        ]
        e = LLMCallEvent(agent_name="A", model="gpt-4o", messages=msgs)
        assert len(e.messages) == 2


class TestLLMResultEvent:
    def test_minimal(self):
        e = LLMResultEvent(agent_name="Planner", model="gpt-4o", output="result")
        assert e.tokens_in == 0
        assert e.tokens_out == 0
        assert e.latency_ms == 0
        assert e.success is True

    def test_with_token_usage(self):
        e = LLMResultEvent(
            agent_name="Planner",
            model="claude-sonnet-4-6",
            output="analysis result",
            tokens_in=1500,
            tokens_out=500,
            latency_ms=2300,
            session_id="s1",
        )
        assert e.tokens_in == 1500
        assert e.tokens_out == 500
        assert e.latency_ms == 2300


class TestToolStartEvent:
    def test_minimal(self):
        e = ToolStartEvent(agent_name="Planner", tool_name="search")
        assert e.tool_name == "search"
        assert e.tool_input == {}

    def test_with_input(self):
        e = ToolStartEvent(
            agent_name="Planner",
            tool_name="calculator",
            tool_input={"expression": "2+2"},
        )
        assert e.tool_input["expression"] == "2+2"


class TestToolEndEvent:
    def test_minimal(self):
        e = ToolEndEvent(agent_name="Planner", tool_name="search", tool_output="results")
        assert e.tool_output == "results"
        assert e.success is True
        assert e.latency_ms == 0

    def test_failure(self):
        e = ToolEndEvent(
            agent_name="Planner",
            tool_name="search",
            tool_output="timeout",
            success=False,
            latency_ms=5000,
        )
        assert e.success is False
        assert e.latency_ms == 5000


class TestAgentErrorEvent:
    def test_minimal(self):
        e = AgentErrorEvent(
            agent_name="Planner",
            error_type="ValueError",
            error_message="invalid input",
        )
        assert e.error_type == "ValueError"
        assert e.error_message == "invalid input"

    def test_timestamp_auto(self):
        e = AgentErrorEvent(
            agent_name="Worker",
            error_type="RuntimeError",
            error_message="crash",
        )
        assert e.timestamp  # auto-filled
        assert e.timestamp.endswith("+00:00") or "Z" in e.timestamp or "+" in e.timestamp
