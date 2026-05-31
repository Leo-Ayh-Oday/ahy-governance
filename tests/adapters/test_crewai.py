"""Tests for CrewAI Adapter — CrewAI 事件桥接。"""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass


# ── Mock CrewAI objects ─────────────────────────────────────────

class MockAgent:
    def __init__(self, role="Planner", model="gpt-4o"):
        self.role = role
        self.llm = MagicMock()
        self.llm.model_name = model


class MockStep:
    def __init__(self, agent=None, output="step output"):
        self.agent = agent or MockAgent()
        self.output = output
        self.result = None


class MockTask:
    def __init__(self, agent=None, description="Analyze data", output="task result"):
        self.agent = agent or MockAgent()
        self.description = description
        self.output = output


# ── Initialization ──────────────────────────────────────────────

@patch("ahy_governance.adapters.crewai._CREWAI_AVAILABLE", True)
class TestInit:
    def test_creates_with_pipeline(self):
        from ahy_governance.adapters.crewai import CrewAIGovernanceCallback
        from ahy_governance.collector import GovernancePipeline
        callback = CrewAIGovernanceCallback(GovernancePipeline())
        assert callback.framework_name == "crewai"

    def test_creates_with_custom_collector(self):
        from ahy_governance.adapters.crewai import CrewAIGovernanceCallback
        collector = MagicMock()
        callback = CrewAIGovernanceCallback(collector)
        assert callback.collector is collector


# ── Agent name extraction ───────────────────────────────────────

class TestAgentNameExtraction:
    def test_from_agent_role(self):
        from ahy_governance.adapters.crewai import CrewAIGovernanceCallback
        agent = MockAgent(role="Analyst")
        assert CrewAIGovernanceCallback._extract_agent_name(agent) == "Analyst"

    def test_from_step_agent(self):
        from ahy_governance.adapters.crewai import CrewAIGovernanceCallback
        step = MockStep(agent=MockAgent(role="Executor"))
        assert CrewAIGovernanceCallback._extract_agent_name(step) == "Executor"

    def test_fallback_name(self):
        from ahy_governance.adapters.crewai import CrewAIGovernanceCallback
        obj = MagicMock(spec=[])  # no role, no agent, no name
        assert CrewAIGovernanceCallback._extract_agent_name(obj) == "crewai-agent"


# ── Model extraction ────────────────────────────────────────────

class TestModelExtraction:
    def test_from_llm_model_name(self):
        from ahy_governance.adapters.crewai import CrewAIGovernanceCallback
        agent = MockAgent(model="claude-sonnet-4-6")
        assert CrewAIGovernanceCallback._extract_model(agent) == "claude-sonnet-4-6"

    def test_no_llm(self):
        from ahy_governance.adapters.crewai import CrewAIGovernanceCallback
        agent = MagicMock()
        agent.llm = None
        assert CrewAIGovernanceCallback._extract_model(agent) == "unknown"


# ── Output extraction ───────────────────────────────────────────

class TestOutputExtraction:
    def test_from_output(self):
        from ahy_governance.adapters.crewai import CrewAIGovernanceCallback
        step = MockStep(output="hello world")
        assert CrewAIGovernanceCallback._extract_output(step) == "hello world"

    def test_from_result(self):
        from ahy_governance.adapters.crewai import CrewAIGovernanceCallback
        step = MockStep()
        step.output = None
        step.result = "from result"
        assert CrewAIGovernanceCallback._extract_output(step) == "from result"

    def test_empty(self):
        from ahy_governance.adapters.crewai import CrewAIGovernanceCallback
        step = MockStep()
        step.output = None
        step.result = None
        step.text = None
        assert CrewAIGovernanceCallback._extract_output(step) == ""


# ── Step callback ───────────────────────────────────────────────

@patch("ahy_governance.adapters.crewai._CREWAI_AVAILABLE", True)
class TestStepCallback:
    def test_on_step_calls_collector(self):
        from ahy_governance.adapters.crewai import CrewAIGovernanceCallback
        collector = MagicMock()
        callback = CrewAIGovernanceCallback(collector)
        step = MockStep(agent=MockAgent(role="Planner"), output="planned")

        callback.on_step(step)

        collector.on_agent_end.assert_called_once()
        event = collector.on_agent_end.call_args[0][0]
        assert event.agent_name == "Planner"
        assert event.output == {"result": "planned"}
        assert event.success is True


# ── Task callback ───────────────────────────────────────────────

@patch("ahy_governance.adapters.crewai._CREWAI_AVAILABLE", True)
class TestTaskCallback:
    def test_on_task_calls_collector(self):
        from ahy_governance.adapters.crewai import CrewAIGovernanceCallback
        collector = MagicMock()
        callback = CrewAIGovernanceCallback(collector)
        task = MockTask(agent=MockAgent(role="Writer"), output="written report")

        callback.on_task(task)

        collector.on_llm_result.assert_called_once()
        event = collector.on_llm_result.call_args[0][0]
        assert event.agent_name == "Writer"
        assert "written report" in event.output


# ── Start step ──────────────────────────────────────────────────

@patch("ahy_governance.adapters.crewai._CREWAI_AVAILABLE", True)
class TestStartStep:
    def test_start_step_calls_on_agent_start(self):
        from ahy_governance.adapters.crewai import CrewAIGovernanceCallback
        collector = MagicMock()
        callback = CrewAIGovernanceCallback(collector)
        agent = MockAgent(role="Researcher")

        callback.start_step(agent)

        collector.on_agent_start.assert_called_once()
        event = collector.on_agent_start.call_args[0][0]
        assert event.agent_name == "Researcher"
        assert event.model == "gpt-4o"
