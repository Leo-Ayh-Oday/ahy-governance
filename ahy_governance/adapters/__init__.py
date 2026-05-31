"""
Framework Adapters — 将各 Agent 框架的原生事件翻译为 ahy-governance 统一事件。

内置适配器:
  - LangChainGovernanceHandler  (langchain)
  - GovernancePipeline          (generic / HTTP webhook)

扩展包命名规范:
  ahy-governance-langchain → LangChain adapter
  ahy-governance-crewai    → CrewAI adapter
"""

from __future__ import annotations

from ..collector import GovernanceCollector

# 适配器注册表
_ADAPTER_REGISTRY: dict[str, type[GovernanceCollector]] = {}


def register_adapter(name: str, adapter_cls: type[GovernanceCollector]) -> None:
    """注册适配器。扩展包在导入时自动调用。"""
    _ADAPTER_REGISTRY[name] = adapter_cls


def list_adapters() -> list[str]:
    """列出已注册的适配器名称。"""
    return list(_ADAPTER_REGISTRY.keys())


def get_adapter(name: str) -> type[GovernanceCollector] | None:
    """按名称获取适配器类。"""
    return _ADAPTER_REGISTRY.get(name)


# 注册内置适配器
from ..collector import GovernancePipeline  # noqa: E402
register_adapter("generic", GovernancePipeline)


# LangChain 适配器（如果 langchain 可用）
try:
    from .langchain import LangChainGovernanceHandler  # noqa: F401
    register_adapter("langchain", LangChainGovernanceHandler)
except ImportError:
    pass


# CrewAI 适配器（如果 crewai 可用）
try:
    from .crewai import CrewAIGovernanceCallback  # noqa: F401
    register_adapter("crewai", CrewAIGovernanceCallback)
except ImportError:
    pass
