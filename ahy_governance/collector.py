"""
GovernanceCollector — 统一治理采集接口 + 默认管道实现。

框架适配器实现 GovernanceCollector ABC，把原生事件翻译成统一格式。
GovernancePipeline 是默认实现，将事件路由到各治理模块。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .events import (
    AgentStartEvent,
    AgentEndEvent,
    LLMCallEvent,
    LLMResultEvent,
    ToolStartEvent,
    ToolEndEvent,
    AgentErrorEvent,
)
from .audit_logger import AuditEventType


class GovernanceCollector(ABC):
    """统一治理采集接口。框架适配器实现此接口。"""

    @abstractmethod
    def on_agent_start(self, event: AgentStartEvent) -> None:
        """Agent 开始执行。"""
        ...

    @abstractmethod
    def on_agent_end(self, event: AgentEndEvent) -> None:
        """Agent 执行完成。"""
        ...

    @abstractmethod
    def on_llm_call(self, event: LLMCallEvent) -> None:
        """LLM 调用发起（推理前）。"""
        ...

    @abstractmethod
    def on_llm_result(self, event: LLMResultEvent) -> None:
        """LLM 调用完成（推理后）。"""
        ...

    def on_tool_start(self, event: ToolStartEvent) -> None:
        """工具调用开始（可选钩子）。"""

    def on_tool_end(self, event: ToolEndEvent) -> None:
        """工具调用结束（可选钩子）。"""

    def on_error(self, event: AgentErrorEvent) -> None:
        """Agent 错误（可选钩子）。"""

    @property
    @abstractmethod
    def framework_name(self) -> str:
        """返回适配器对应的框架名称，如 'langchain'、'crewai'、'generic'。"""
        ...


class GovernancePipeline(GovernanceCollector):
    """默认治理管道。将事件路由到 HealthMonitor / CostTracker / AuditReporter。

    用法::

        pipeline = GovernancePipeline(workspace_id="ws-1")
        pipeline.on_llm_result(LLMResultEvent(
            agent_name="Planner", model="claude-sonnet-4-6",
            output="...", tokens_in=1500, tokens_out=500,
            latency_ms=2300, session_id="sess-1",
        ))
    """

    def __init__(self, workspace_id: str = ""):
        self.workspace_id = workspace_id

    # ── Agent lifecycle ──────────────────────────────────────────

    def on_agent_start(self, event: AgentStartEvent) -> None:
        from .health_monitor import get_monitor
        from .audit_logger import get_auditor

        get_monitor().heartbeat(
            event.agent_name, "ok", 0, self.workspace_id,
        )
        get_auditor().log(
            AuditEventType.AGENT_START, event.agent_name,
            {"model": event.model, "input": event.input},
            event.session_id, workspace_id=self.workspace_id,
        )
        # Save checkpoint for context recovery
        if event.input:
            from .checkpoint_store import get_checkpoint_store
            get_checkpoint_store().save(
                event.agent_name, event.session_id, event.input,
                step="start", workspace_id=self.workspace_id,
            )

    def on_agent_end(self, event: AgentEndEvent) -> None:
        from .health_monitor import get_monitor
        from .audit_logger import get_auditor

        status = "ok" if event.success else "error"
        get_monitor().heartbeat(
            event.agent_name, status, event.total_latency_ms,
            self.workspace_id,
        )
        get_auditor().log(
            AuditEventType.AGENT_COMPLETE, event.agent_name,
            {
                "output": event.output,
                "success": event.success,
                "total_latency_ms": event.total_latency_ms,
            },
            event.session_id, workspace_id=self.workspace_id,
        )
        # Save checkpoint on completion
        from .checkpoint_store import get_checkpoint_store
        get_checkpoint_store().save(
            event.agent_name, event.session_id,
            {"output": event.output, "success": event.success},
            step="end", workspace_id=self.workspace_id,
        )

    # ── LLM hooks ────────────────────────────────────────────────

    def on_llm_call(self, event: LLMCallEvent) -> None:
        pass  # 成本在 on_llm_result 中计算，此处预留

    def on_llm_result(self, event: LLMResultEvent) -> None:
        from .health_monitor import get_monitor
        from .cost_tracker import get_tracker

        get_monitor().record_call(
            event.agent_name, event.success, event.latency_ms,
            event.session_id, self.workspace_id,
        )
        if event.tokens_in and event.tokens_out:
            try:
                get_tracker().track(
                    event.agent_name, event.model,
                    event.tokens_in, event.tokens_out,
                    event.session_id, self.workspace_id,
                )
            except KeyError:
                pass  # 模型未注册定价，跳过成本追踪

    # ── Tool hooks ───────────────────────────────────────────────

    def on_tool_end(self, event: ToolEndEvent) -> None:
        from .audit_logger import get_auditor

        get_auditor().log(
            AuditEventType.TOOL_CALL, event.agent_name,
            {
                "tool": event.tool_name,
                "output": event.tool_output,
                "success": event.success,
                "latency_ms": event.latency_ms,
            },
            event.session_id, workspace_id=self.workspace_id,
        )

    # ── Error hook ───────────────────────────────────────────────

    _ERROR_TYPE_MAP: dict[str, str] = {
        "timeout": "timeout", "TimeoutError": "timeout",
        "rate_limit": "rate_limit", "RateLimitError": "rate_limit",
        "auth": "auth_error", "AuthenticationError": "auth_error",
        "permission": "auth_error", "PermissionError": "auth_error",
        "memory": "memory_exhausted", "MemoryError": "memory_exhausted",
        "validation": "output_invalid", "ValidationError": "output_invalid",
        "schema": "output_invalid", "SchemaError": "output_invalid",
        "connection": "timeout", "ConnectionError": "timeout",
        "dependency": "dependency_failure",
        "runtime": "execution_error", "RuntimeError": "execution_error",
        "exception": "execution_error",
    }

    @classmethod
    def _map_error_to_incident(cls, error_type: str) -> str:
        if not error_type:
            return "unknown"
        lower = error_type.lower()
        for key, incident in cls._ERROR_TYPE_MAP.items():
            if key.lower() in lower:
                return incident
        return "unknown"

    def on_error(self, event: AgentErrorEvent) -> None:
        from .health_monitor import get_monitor
        from .audit_logger import get_auditor

        get_monitor().heartbeat(
            event.agent_name, "error", 0, self.workspace_id,
        )
        get_auditor().log(
            AuditEventType.AGENT_ERROR, event.agent_name,
            {"error": event.error_message, "type": event.error_type},
            event.session_id, workspace_id=self.workspace_id,
        )
        # Auto-trigger self-healing
        from .self_healer import get_healer, IncidentType
        from .checkpoint_store import get_checkpoint_store

        incident_type = self._map_error_to_incident(event.error_type)
        try:
            it = IncidentType(incident_type)
        except ValueError:
            it = IncidentType.UNKNOWN

        checkpoint = get_checkpoint_store().load_latest(
            event.agent_name, event.session_id, self.workspace_id,
        )
        ctx = {
            "error_type": event.error_type,
            "session_id": event.session_id,
        }
        if checkpoint:
            ctx["checkpoint"] = checkpoint.to_dict()

        get_healer().self_heal(
            event.agent_name, it, event.error_message,
            context=ctx, workspace_id=self.workspace_id,
        )

    # ── Identity ─────────────────────────────────────────────────

    @property
    def framework_name(self) -> str:
        return "generic"
