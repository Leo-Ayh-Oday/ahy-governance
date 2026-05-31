"""
Governance Events — 框架无关的统一治理事件格式。

所有框架适配器将原生事件翻译为此处定义的 7 种事件，
然后推入 GovernancePipeline 进行分发。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentStartEvent:
    agent_name: str
    agent_id: str = ""
    model: str = ""
    input: dict | None = None
    session_id: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = _now()
        if self.input is None:
            self.input = {}

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AgentEndEvent:
    agent_name: str
    output: dict | None = None
    success: bool = True
    total_latency_ms: float = 0
    session_id: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = _now()
        if self.output is None:
            self.output = {}

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LLMCallEvent:
    agent_name: str
    model: str
    messages: list[dict]
    tokens_in: int = 0
    session_id: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = _now()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LLMResultEvent:
    agent_name: str
    model: str
    output: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0
    success: bool = True
    session_id: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = _now()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ToolStartEvent:
    agent_name: str
    tool_name: str
    tool_input: dict = field(default_factory=dict)
    session_id: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = _now()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ToolEndEvent:
    agent_name: str
    tool_name: str
    tool_output: str
    success: bool = True
    latency_ms: float = 0
    session_id: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = _now()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AgentErrorEvent:
    agent_name: str
    error_type: str
    error_message: str
    session_id: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = _now()

    def to_dict(self) -> dict:
        return asdict(self)
