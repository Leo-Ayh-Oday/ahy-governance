# 框架适配器系统 — 详细实施方案

## 一、架构总览

```
                        ahy-governance 核心
                    ┌─────────────────────────┐
                    │  ConflictDetector        │
                    │  CostTracker             │
                    │  AuditReporter           │
                    │  HealthMonitor           │
                    │  PromptGuard             │
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │   GovernanceCollector    │  ← 新增：统一采集接口
                    │   (ABC 抽象类)           │
                    └──────────┬──────────────┘
                               │
            ┌──────────────────┼──────────────────┐
            │                  │                  │
    ┌───────▼──────┐  ┌───────▼──────┐  ┌───────▼──────┐
    │  LangChain   │  │   CrewAI     │  │   Generic    │
    │  Adapter     │  │   Adapter    │  │   HTTP       │
    │              │  │              │  │   Webhook    │
    └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
           │                 │                  │
    ┌──────▼──────┐  ┌──────▼──────┐  ┌───────▼──────┐
    │ LangChain   │  │   CrewAI    │  │  任何HTTP    │
    │ Agent 应用  │  │   Agent 应用│  │  Agent 服务  │
    └─────────────┘  └─────────────┘  └──────────────┘
```

**核心思路**：每个 Agent 框架在关键生命周期节点（开始、推理、工具调用、结束）触发钩子，适配器把框架原生事件翻译成 ahy-governance 统一格式，推入治理管道。

## 二、GovernanceCollector 接口设计

新增文件：`ahy_governance/collector.py`

```python
class GovernanceCollector(ABC):
    """统一治理采集接口。框架适配器实现此接口。"""

    # ── 生命周期钩子 ──
    @abstractmethod
    def on_agent_start(self, event: AgentStartEvent) -> None: ...
    @abstractmethod
    def on_agent_end(self, event: AgentEndEvent) -> None: ...

    # ── 推理钩子（核心）──
    @abstractmethod
    def on_llm_call(self, event: LLMCallEvent) -> None: ...
    @abstractmethod
    def on_llm_result(self, event: LLMResultEvent) -> None: ...

    # ── 工具调用钩子 ──
    def on_tool_start(self, event: ToolStartEvent) -> None: ...  # 可选
    def on_tool_end(self, event: ToolEndEvent) -> None: ...      # 可选

    # ── 冲突/错误钩子 ──
    def on_error(self, event: AgentErrorEvent) -> None: ...      # 可选

    # ── 标识 ──
    @property
    @abstractmethod
    def framework_name(self) -> str: ...
```

**事件数据类**（`ahy_governance/events.py`）：

```python
@dataclass
class AgentStartEvent:
    agent_name: str
    agent_id: str = ""
    model: str = ""
    input: dict | None = None
    session_id: str = ""
    timestamp: str = ""  # ISO 8601

@dataclass
class LLMCallEvent:
    agent_name: str
    model: str
    messages: list[dict]
    tokens_in: int = 0
    session_id: str = ""
    timestamp: str = ""

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

@dataclass
class ToolStartEvent:
    agent_name: str
    tool_name: str
    tool_input: dict
    session_id: str = ""
    timestamp: str = ""

@dataclass  
class ToolEndEvent:
    agent_name: str
    tool_name: str
    tool_output: str
    success: bool = True
    latency_ms: float = 0
    session_id: str = ""
    timestamp: str = ""

@dataclass
class AgentEndEvent:
    agent_name: str
    output: dict | None = None
    success: bool = True
    total_latency_ms: float = 0
    session_id: str = ""
    timestamp: str = ""

@dataclass
class AgentErrorEvent:
    agent_name: str
    error_type: str
    error_message: str
    session_id: str = ""
    timestamp: str = ""
```

## 三、核心管道：GovernancePipeline

```python
class GovernancePipeline(GovernanceCollector):
    """
    默认采集器实现。把事件路由到各治理模块：
      LLMCallEvent  → CostTracker.track()
      LLMResultEvent → HealthMonitor.record_call()
      AgentStartEvent → AuditReporter.log()
      AgentEndEvent → AuditReporter.log()
      AgentErrorEvent → AuditReporter.log() + HealthMonitor
      ToolStartEvent → ConflictDetector.check()
    """

    def __init__(self, workspace_id: str = ""):
        self.workspace_id = workspace_id

    def on_agent_start(self, event: AgentStartEvent):
        get_monitor().heartbeat(event.agent_name, "ok", 0, self.workspace_id)
        get_auditor().log(AuditEventType.AGENT_START, event.agent_name,
                          {"model": event.model, "input": event.input},
                          event.session_id, workspace_id=self.workspace_id)

    def on_llm_call(self, event: LLMCallEvent):
        # 成本在 LLMResult 时计算，这里仅记录调用意图
        pass

    def on_llm_result(self, event: LLMResultEvent):
        get_monitor().record_call(event.agent_name, event.success,
                                  event.latency_ms, event.session_id,
                                  self.workspace_id)
        # 如果在 proxy 模式，自动提取成本
        if event.tokens_in and event.tokens_out:
            try:
                get_tracker().track(event.agent_name, event.model,
                                    event.tokens_in, event.tokens_out,
                                    event.session_id, self.workspace_id)
            except KeyError:
                pass  # 模型未注册 pricing，跳过成本追踪

    def on_tool_end(self, event: ToolEndEvent):
        get_auditor().log(AuditEventType.TOOL_CALL, event.agent_name,
                          {"tool": event.tool_name, "success": event.success},
                          event.session_id, workspace_id=self.workspace_id)

    def on_error(self, event: AgentErrorEvent):
        get_monitor().heartbeat(event.agent_name, "error", 0, self.workspace_id)
        get_auditor().log(AuditEventType.ERROR, event.agent_name,
                          {"error": event.error_message, "type": event.error_type},
                          event.session_id, workspace_id=self.workspace_id)

    @property
    def framework_name(self) -> str:
        return "generic"
```

## 四、Phase 1：LangChain Adapter

**文件**：`ahy_governance/adapters/langchain.py`

```python
from langchain.callbacks.base import BaseCallbackHandler
from ahy_governance.collector import GovernanceCollector
from ahy_governance.events import *

class LangChainGovernanceHandler(BaseCallbackHandler):
    """LangChain callback → GovernanceCollector 事件桥接。

    用法：
        from ahy_governance.adapters.langchain import LangChainGovernanceHandler
        from ahy_governance.collector import GovernancePipeline

        handler = LangChainGovernanceHandler(GovernancePipeline(workspace_id="ws-1"))
        agent = create_agent(callbacks=[handler])
    """

    def __init__(self, collector: GovernanceCollector):
        self.collector = collector
        self._call_times: dict[str, float] = {}

    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, **kwargs):
        agent_name = self._resolve_agent_name(serialized)
        self._call_times[run_id] = time.time()
        self.collector.on_agent_start(AgentStartEvent(
            agent_name=agent_name,
            input=inputs if isinstance(inputs, dict) else {"input": str(inputs)},
            session_id=str(parent_run_id or run_id),
        ))

    def on_llm_start(self, serialized, prompts, *, run_id, parent_run_id=None, **kwargs):
        model = serialized.get("kwargs", {}).get("model_name", "unknown")
        agent_name = self._resolve_agent_name(serialized)
        self.collector.on_llm_call(LLMCallEvent(
            agent_name=agent_name, model=model,
            messages=[{"content": p} for p in prompts],
            session_id=str(parent_run_id or run_id),
        ))

    def on_llm_end(self, response, *, run_id, parent_run_id=None, **kwargs):
        elapsed = time.time() - self._call_times.pop(run_id, time.time())
        llm_result = response.generations[0][0] if response.generations else None
        agent_name = "agent"
        self.collector.on_llm_result(LLMResultEvent(
            agent_name=agent_name,
            model=getattr(response, "model_name", "unknown"),
            output=llm_result.text if llm_result else "",
            tokens_in=getattr(response.llm_output or {}, "token_usage", {}).get("prompt_tokens", 0),
            tokens_out=getattr(response.llm_output or {}, "token_usage", {}).get("completion_tokens", 0),
            latency_ms=round(elapsed * 1000, 1),
            session_id=str(parent_run_id or run_id),
        ))

    def on_tool_end(self, output, *, run_id, parent_run_id=None, **kwargs):
        self.collector.on_tool_end(ToolEndEvent(
            agent_name="agent",
            tool_name=kwargs.get("name", "unknown"),
            tool_output=str(output),
            session_id=str(parent_run_id or run_id),
        ))

    def on_chain_end(self, outputs, *, run_id, parent_run_id=None, **kwargs):
        elapsed = time.time() - self._call_times.pop(run_id, time.time())
        self.collector.on_agent_end(AgentEndEvent(
            agent_name="agent",
            output=outputs if isinstance(outputs, dict) else {"output": str(outputs)},
            total_latency_ms=round(elapsed * 1000, 1),
            session_id=str(parent_run_id or run_id),
        ))

    def _resolve_agent_name(self, serialized: dict) -> str:
        return serialized.get("name") or serialized.get("id", ["agent"])[-1]

    @property
    def framework_name(self) -> str:
        return "langchain"
```

## 五、插件注册与发现

在 `__init__.py` 中增加适配器注册：

```python
# 适配器注册表
_ADAPTER_REGISTRY: dict[str, type[GovernanceCollector]] = {}

def register_adapter(name: str, adapter_cls: type[GovernanceCollector]):
    _ADAPTER_REGISTRY[name] = adapter_cls

def list_adapters() -> list[str]:
    return list(_ADAPTER_REGISTRY.keys())

def get_adapter(name: str) -> type[GovernanceCollector] | None:
    return _ADAPTER_REGISTRY.get(name)
```

**PyPI 扩展包命名规范**：`ahy-governance-langchain`、`ahy-governance-crewai`

每个扩展包是一个独立 PyPI 项目，依赖 `ahy-governance` 核心，安装后自动注册。

## 六、实施步骤

### Phase 1：LangChain Adapter（3-4 小时）

| 步骤 | 文件 | 内容 |
|------|------|------|
| 1.1 | `ahy_governance/events.py` | 6 个事件 dataclass |
| 1.2 | `ahy_governance/collector.py` | `GovernanceCollector` ABC + `GovernancePipeline` |
| 1.3 | `ahy_governance/adapters/__init__.py` | 适配器包 |
| 1.4 | `ahy_governance/adapters/langchain.py` | LangChain callback handler |
| 1.5 | `tests/test_collector.py` | Pipeline 单元测试（mock 事件） |
| 1.6 | `tests/adapters/test_langchain.py` | LangChain 集成测试 |

### Phase 2：接口稳定 + CrewAI（2-3 小时）

| 步骤 | 内容 |
|------|------|
| 2.1 | 修复 Phase 1 发现的问题，稳定事件接口 |
| 2.2 | `ahy_governance/adapters/crewai.py` | CrewAI adapter |
| 2.3 | 提取适配器开发指南 `docs/ADAPTERS.md` |

### Phase 3：生态发布（1-2 小时）

| 步骤 | 内容 |
|------|------|
| 3.1 | 创建 `ahy-governance-langchain` PyPI 包 |
| 3.2 | 创建 `ahy-governance-crewai` PyPI 包 |
| 3.3 | GitHub 上发布 Adapter 开发模板仓库 |

## 七、测试策略

```
tests/
├── test_collector.py           # GovernancePipeline 单元测试
├── test_events.py              # 事件序列化/反序列化
└── adapters/
    ├── __init__.py
    ├── test_langchain.py        # LangChain handler 测试
    └── test_crewai.py           # CrewAI adapter 测试
```

**每类测试覆盖：**
- 事件正确创建和字段完整性
- Pipeline 正确路由事件到对应模块
- Adapter 正确翻译框架事件到 GovernanceCollector 事件
- 错误情况：缺失字段、异常调用顺序、超长输入

## 八、预期结果

完成后，用户只需 3 行代码接入治理：

```python
from ahy_governance.adapters.langchain import LangChainGovernanceHandler
from ahy_governance.collector import GovernancePipeline

handler = LangChainGovernanceHandler(GovernancePipeline(workspace_id="ws-1"))

# 原有 LangChain 代码不改，只加 callbacks
agent = initialize_agent(tools, llm, callbacks=[handler])
result = agent.run("分析这份合同的风险")
# → Dashboard 实时显示健康状态、Token 消耗、审计日志
```
