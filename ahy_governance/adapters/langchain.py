"""
LangChain Adapter — 将 LangChain callback 事件桥接到 GovernanceCollector。

用法::

    from ahy_governance.adapters.langchain import LangChainGovernanceHandler
    from ahy_governance.collector import GovernancePipeline

    handler = LangChainGovernanceHandler(GovernancePipeline(workspace_id="ws-1"))
    agent = initialize_agent(tools, llm, callbacks=[handler])
    result = agent.run("分析这份合同的风险")
"""

from __future__ import annotations

import time

try:
    from langchain.callbacks.base import BaseCallbackHandler
    _LANGCHAIN_AVAILABLE = True
except ImportError:
    BaseCallbackHandler = object  # type: ignore[assignment,misc]
    _LANGCHAIN_AVAILABLE = False

from ..collector import GovernanceCollector
from ..events import (
    AgentStartEvent,
    AgentEndEvent,
    LLMCallEvent,
    LLMResultEvent,
    ToolStartEvent,
    ToolEndEvent,
    AgentErrorEvent,
)


class LangChainGovernanceHandler(BaseCallbackHandler):
    """LangChain callback → GovernanceCollector 事件桥接。

    映射关系:
      on_chain_start  → AgentStartEvent
      on_llm_start    → LLMCallEvent
      on_llm_end      → LLMResultEvent
      on_tool_start   → ToolStartEvent
      on_tool_end     → ToolEndEvent
      on_chain_end    → AgentEndEvent
      on_chain_error  → AgentErrorEvent
    """

    def __init__(self, collector: GovernanceCollector):
        if not _LANGCHAIN_AVAILABLE:
            raise ImportError(
                "langchain is required to use LangChainGovernanceHandler. "
                "Install it with: pip install langchain"
            )
        self.collector = collector
        self._call_times: dict[str, float] = {}
        self._agent_names: dict[str, str] = {}

    # ── Chain lifecycle ──────────────────────────────────────────

    def on_chain_start(
        self, serialized: dict, inputs: dict, *,
        run_id: str, parent_run_id: str | None = None, **kwargs,
    ) -> None:
        agent_name = self._resolve_agent_name(serialized)
        self._call_times[run_id] = time.time()
        self._agent_names[run_id] = agent_name

        safe_input = inputs if isinstance(inputs, dict) else {"input": str(inputs)}
        self.collector.on_agent_start(AgentStartEvent(
            agent_name=agent_name,
            agent_id=serialized.get("id", [agent_name])[-1] if isinstance(serialized.get("id"), list) else agent_name,
            input=safe_input,
            session_id=str(parent_run_id or run_id),
        ))

    def on_chain_end(
        self, outputs: dict, *, run_id: str,
        parent_run_id: str | None = None, **kwargs,
    ) -> None:
        agent_name = self._agent_names.pop(run_id, "agent")
        elapsed = time.time() - self._call_times.pop(run_id, time.time())
        safe_output = outputs if isinstance(outputs, dict) else {"output": str(outputs)}
        self.collector.on_agent_end(AgentEndEvent(
            agent_name=agent_name,
            output=safe_output,
            total_latency_ms=round(elapsed * 1000, 1),
            session_id=str(parent_run_id or run_id),
        ))

    def on_chain_error(
        self, error: Exception, *, run_id: str,
        parent_run_id: str | None = None, **kwargs,
    ) -> None:
        agent_name = self._agent_names.get(run_id, "agent")
        self.collector.on_error(AgentErrorEvent(
            agent_name=agent_name,
            error_type=type(error).__name__,
            error_message=str(error),
            session_id=str(parent_run_id or run_id),
        ))

    # ── LLM hooks ────────────────────────────────────────────────

    def on_llm_start(
        self, serialized: dict, prompts: list[str], *,
        run_id: str, parent_run_id: str | None = None, **kwargs,
    ) -> None:
        model = ""
        if isinstance(serialized.get("kwargs"), dict):
            model = serialized["kwargs"].get("model_name", "")
        if not model:
            model = serialized.get("name", "unknown")

        parent_agent = self._agent_names.get(str(parent_run_id or ""), "agent")
        self._call_times[run_id] = time.time()
        self._agent_names[run_id] = parent_agent

        self.collector.on_llm_call(LLMCallEvent(
            agent_name=parent_agent,
            model=model,
            messages=[{"content": p} for p in prompts],
            session_id=str(parent_run_id or run_id),
        ))

    def on_llm_end(
        self, response, *, run_id: str,
        parent_run_id: str | None = None, **kwargs,
    ) -> None:
        agent_name = self._agent_names.pop(run_id, "agent")
        elapsed = time.time() - self._call_times.pop(run_id, time.time())

        llm_output = ""
        tokens_in = 0
        tokens_out = 0
        model = "unknown"

        if hasattr(response, "generations") and response.generations:
            gen = response.generations[0][0] if response.generations[0] else None
            if gen and hasattr(gen, "text"):
                llm_output = gen.text or ""

        if hasattr(response, "model_name"):
            model = response.model_name

        if hasattr(response, "llm_output") and isinstance(response.llm_output, dict):
            tu = response.llm_output.get("token_usage", {})
            if isinstance(tu, dict):
                tokens_in = tu.get("prompt_tokens", 0)
                tokens_out = tu.get("completion_tokens", 0)

        self.collector.on_llm_result(LLMResultEvent(
            agent_name=agent_name,
            model=model,
            output=llm_output,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=round(elapsed * 1000, 1),
            session_id=str(parent_run_id or run_id),
        ))

    # ── Tool hooks ───────────────────────────────────────────────

    def on_tool_start(
        self, serialized: dict, input_str: str, *,
        run_id: str, parent_run_id: str | None = None, **kwargs,
    ) -> None:
        agent_name = self._agent_names.get(str(parent_run_id or ""), "agent")
        tool_name = serialized.get("name", "unknown")
        self._call_times[run_id] = time.time()

        self.collector.on_tool_start(ToolStartEvent(
            agent_name=agent_name,
            tool_name=tool_name,
            tool_input={"input": input_str},
            session_id=str(parent_run_id or run_id),
        ))

    def on_tool_end(
        self, output: str, *, run_id: str,
        parent_run_id: str | None = None, name: str = "", **kwargs,
    ) -> None:
        agent_name = self._agent_names.get(str(parent_run_id or ""), "agent")
        elapsed = time.time() - self._call_times.pop(run_id, time.time())

        self.collector.on_tool_end(ToolEndEvent(
            agent_name=agent_name,
            tool_name=name or "unknown",
            tool_output=str(output),
            latency_ms=round(elapsed * 1000, 1),
            session_id=str(parent_run_id or run_id),
        ))

    def on_tool_error(
        self, error: Exception, *, run_id: str,
        parent_run_id: str | None = None, name: str = "", **kwargs,
    ) -> None:
        agent_name = self._agent_names.get(str(parent_run_id or ""), "agent")
        elapsed = time.time() - self._call_times.pop(run_id, time.time())

        self.collector.on_tool_end(ToolEndEvent(
            agent_name=agent_name,
            tool_name=name or "unknown",
            tool_output=str(error),
            success=False,
            latency_ms=round(elapsed * 1000, 1),
            session_id=str(parent_run_id or run_id),
        ))

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _resolve_agent_name(serialized: dict) -> str:
        name = serialized.get("name")
        if name:
            return name
        id_val = serialized.get("id")
        if isinstance(id_val, list) and id_val:
            return id_val[-1]
        return "agent"

    @property
    def framework_name(self) -> str:
        return "langchain"
