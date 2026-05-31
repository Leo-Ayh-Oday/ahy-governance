"""
CrewAI Adapter — 将 CrewAI callback 事件桥接到 GovernanceCollector。

用法::

    from ahy_governance.adapters.crewai import CrewAIGovernanceCallback
    from ahy_governance.collector import GovernancePipeline

    callback = CrewAIGovernanceCallback(GovernancePipeline(workspace_id="ws-1"))
    crew = Crew(agents=[...], tasks=[...], step_callback=callback.on_step, task_callback=callback.on_task)
    crew.kickoff()

映射关系:
    step_callback → AgentStartEvent / AgentEndEvent (per agent step)
    task_callback → LLMResultEvent (per task completion)
"""

from __future__ import annotations

import time
from typing import Any, Callable

try:
    from crewai import Agent, Task, Crew
    _CREWAI_AVAILABLE = True
except ImportError:
    _CREWAI_AVAILABLE = False

from ..collector import GovernanceCollector
from ..events import (
    AgentStartEvent,
    AgentEndEvent,
    LLMCallEvent,
    LLMResultEvent,
)


class CrewAIGovernanceCallback:
    """CrewAI → GovernanceCollector 事件桥接。

    CrewAI 使用 step_callback 和 task_callback 两个回调:
    - step_callback: 每个 Agent step 结束后调用
    - task_callback: 每个 Task 完成后调用
    """

    def __init__(self, collector: GovernanceCollector):
        if not _CREWAI_AVAILABLE:
            raise ImportError(
                "crewai is required to use CrewAIGovernanceCallback. "
                "Install it with: pip install ahy-governance[crewai]"
            )
        self.collector = collector
        self._step_times: dict[str, float] = {}
        self._current_agent: str = ""
        self._current_model: str = ""

    def on_step(self, step: Any) -> None:
        """Called after each agent step in CrewAI.

        Args:
            step: CrewAI step object. May have attributes:
                  - agent: Agent object with .role, .llm
                  - output: step output text
                  - action: action taken
                  - result: step result
        """
        agent_name = self._extract_agent_name(step)
        model = self._extract_model(step)
        session_id = f"crew-{id(step)}"

        elapsed_ms = 0
        step_key = f"step-{id(step)}"
        if step_key in self._step_times:
            elapsed_ms = (time.time() - self._step_times.pop(step_key)) * 1000

        output_str = self._extract_output(step)

        self.collector.on_agent_end(AgentEndEvent(
            agent_name=agent_name,
            output={"result": output_str} if output_str else None,
            success=True,
            total_latency_ms=round(elapsed_ms, 1),
            session_id=session_id,
        ))

    def on_task(self, task: Any) -> None:
        """Called after each task completion in CrewAI.

        Args:
            task: CrewAI Task object. May have attributes:
                  - agent: Agent object
                  - output: task output
                  - description: task description
                  - expected_output: expected output format
        """
        agent_name = "unknown"
        model = "unknown"

        if hasattr(task, "agent") and task.agent is not None:
            agent_name = self._extract_agent_name(task.agent)
            model = self._extract_model(task.agent)

        output_str = ""
        if hasattr(task, "output") and task.output is not None:
            output_str = str(task.output)[:500]

        tokens_in = max(1, len(getattr(task, "description", "")) // 4) if hasattr(task, "description") else 0
        tokens_out = max(1, len(output_str) // 4) if output_str else 0

        self.collector.on_llm_result(LLMResultEvent(
            agent_name=agent_name,
            model=model,
            output=output_str,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        ))

    def start_step(self, agent: Any) -> None:
        """Mark the start of an agent step (call before step execution).

        Args:
            agent: CrewAI Agent object
        """
        agent_name = self._extract_agent_name(agent)
        model = self._extract_model(agent)
        self._current_agent = agent_name
        self._current_model = model

        step_key = f"step-{id(agent)}"
        self._step_times[step_key] = time.time()

        self.collector.on_agent_start(AgentStartEvent(
            agent_name=agent_name,
            model=model,
        ))

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _extract_agent_name(obj: Any) -> str:
        """Extract agent name from a CrewAI object."""
        if hasattr(obj, "role"):
            return str(obj.role)
        if hasattr(obj, "agent") and hasattr(obj.agent, "role"):
            return str(obj.agent.role)
        if hasattr(obj, "name"):
            return str(obj.name)
        return "crewai-agent"

    @staticmethod
    def _extract_model(obj: Any) -> str:
        """Extract model name from a CrewAI agent."""
        llm = getattr(obj, "llm", None)
        if llm is None:
            return "unknown"
        if hasattr(llm, "model_name"):
            return str(llm.model_name)
        if hasattr(llm, "model"):
            return str(llm.model)
        return str(llm)

    @staticmethod
    def _extract_output(step: Any) -> str:
        """Extract output text from a CrewAI step."""
        if hasattr(step, "output") and step.output is not None:
            return str(step.output)[:500]
        if hasattr(step, "result") and step.result is not None:
            return str(step.result)[:500]
        if hasattr(step, "text") and step.text is not None:
            return str(step.text)[:500]
        return ""

    @property
    def framework_name(self) -> str:
        return "crewai"
