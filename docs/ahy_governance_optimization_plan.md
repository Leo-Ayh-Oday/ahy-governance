# Ahy Governance 完整优化与改进计划

> **基线 Commit**：`6345978`（`main`，2026-07-31）
> **基线 Tag 参考**：`v0.9.2-autoheal`、`v0.9.1-learner`、`v0.9.1-deepseek-doctor`
> **计划修订**：2026-07-31（v2，根据代码审计 + 工程可行性重写范围、迁移策略和 PR 序列）

---

## 0. 计划定位

**当前版本基线：** `main` @ `6345978`（`v0.9.2-autoheal` + 14 commits）

**目标：** 将现有"治理 SDK + MCP 工具集 + Dashboard 原型"收敛为具备统一决策、强制执行、结果验证和证据审计的多 Agent 治理控制面。

**实施假设：** 1 名主开发工程师，配合 Codex/Claude Code 等 AI 编码工具；必要时由 1 名前端或测试人员短期协助。

**主线周期：** 10 周（v0.10 控制闭环 MVP）。

**后续版本：** v0.11（运行控制扩展，3–4 周），v0.12（恢复与质量闭环，4–6 周）。

**核心原则：** 不横向扩展独立模块，将现有模块通过 GovernanceGateway 收敛为统一控制闭环——先完成真实性、安全性和最小治理闭环，再逐步扩展。

**实际能力基线（2026-07-31）：**

| 模块 | 代码状态 | 控制链路状态 |
|------|---------|-------------|
| SelfHealer | 526 行，完整决策链：故障识别 → RecoveryAction → RecoveryLedger → HealResult | **缺执行器**：`_finalize()` 写入 `ATTEMPTED`，不真正执行重试/回滚/熔断 |
| RecoveryLearner | 255 行，可从 ledger 学习规则 | 规则默认 Disabled，未闭环 |
| LLMDoctor | 122 行，可生成结构化 RecoveryAction | 生成后无人执行 |
| CheckpointStore | 105 行，可保存/恢复上下文 | 只返回 `restore_context`，无真正 Resume Adapter |
| PolicyEngine | 533 行，Level 0-5 + 15 风险类 | 独立 API，未接入统一决策管道 |
| Evaluator | 365 行，dataset + scorer 编排 | `run_eval()` 评分对象错误（input 当 output） |
| QualityGate | 121 行 | 无 AgentRunner，无 CI 阻断退出码 |
| CrewAI Adapter | 141 行 | 计时混用 `id(agent)`/`id(step)`，无 before-step hook |

**关键结论：** 瓶颈不是模块数量，而是——决策链散落在各模块中，没有统一的执行器、验证器和路由层。

---

# 1. 最终目标

完成后，平台的标准运行链应统一为：

```text
Agent / Framework / MCP Client
              │
              ▼
       事件标准化与身份解析
              │
              ▼
       GovernanceGateway（唯一路由层）
              │
              ▼
       Governance Runtime
              │
   ┌──────────┼──────────┐
   ▼          ▼          ▼
规则评估   成本/健康   冲突/质量
   └──────────┼──────────┘
              ▼
       Governance Decision
  ALLOW / WARN / BLOCK / REDACT
  RETRY / THROTTLE / ESCALATE
              │
              ▼
       Enforcement Adapter
              │
              ▼
       Enforcement Verifier
              │
              ▼
       Evidence / Audit Ledger
              │
              ▼
  Recovery Learner / Cost Advisor
```

平台必须明确区分四类职责：

1. **Evaluator：** 判断应该采取什么治理动作。
2. **Decision Engine：** 汇总多个 Evaluator，形成唯一决定。
3. **Enforcer：** 真正阻断、脱敏、重试、降级、熔断或升级。
4. **Verifier：** 确认治理动作已经生效，再写入成功证据。

---

# 2. 关键验收指标

以下指标全部满足前，不建议宣称"生产级多 Agent 治理平台"。

| 指标 | 目标 |
|---|---:|
| 治理事件包含 `workspace_id / agent_id / session_id / trace_id` | 100% |
| 非公开 Web API 完成真实身份认证 | 100% |
| 所有 BLOCK 决定均有执行结果 | 100% |
| 所有自愈成功记录均有动作验证证据 | 100% |
| 审计链可跨进程重启恢复 | 100% |
| 多租户隔离测试通过 | 100% |
| SDK 文档示例可复制运行 | 100% |
| Quality Gate 评估真实 Agent 输出 | 100% |
| 核心规则决策 P95 延迟 | < 20 ms |
| 治理主链集成测试 | ≥ 30 个真实场景 |
| 总测试覆盖率 | ≥ 85% |
| 核心控制面覆盖率 | ≥ 90% |
| P0/P1 已知缺陷 | 0 个未处置 |
| **main 分支 CI 全绿** | **100% 的 PR 合并前** |

---

# 3. 当前阶段不应继续做的事情

在 GovernanceGateway 和最小 Runtime 闭环完成前，暂停以下方向：

- 新增更多策略目录；
- 新增更多 Dashboard 页面；
- 新增更多 MCP 工具；
- 宣传"全自动自愈"；
- 宣传"不可篡改审计"；
- 宣传"SOC2/ISO 已合规"；
- 增加新的 Agent 框架适配器；
- 引入 Kafka、Kubernetes 或微服务；
- 为尚未接线的模块继续增加复杂 LLM 能力；
- **将现有大模块（PolicyEngine、Evaluator、SelfHealer 等）整体搬入 `runtime/` 或重写**——它们保留为领域引擎，通过 Adapter 接入新 Runtime。

**原因：** 当前瓶颈不是能力数量，而是能力没有形成统一控制闭环。修复方式是收敛，不是重写。

---

# 4. 渐进迁移策略（核心架构决策）

## 4.1 总体策略：Branch by Abstraction + Strangler Migration

不一次性替换所有模块。每次迁移一项能力，跑通一条完整的"评估→决策→执行→验证→审计"闭环。

## 4.2 新增唯一路由层：GovernanceGateway

所有外部入口最终只允许调用同一路由层：

```text
Web ─┐
MCP ─┼─→ GovernanceGateway
SDK ─┘
```

Gateway 再根据配置决定某项能力走哪条路径。

## 4.3 路由不是全局开关，而是按能力配置

```yaml
routes:
  prompt_guard: runtime
  budget: shadow
  conflict: legacy
  health: legacy
  self_healing: legacy
  quality_gate: legacy
```

四种路由状态：

| 状态 | 含义 |
|------|------|
| `legacy` | 完全走现有模块 |
| `shadow` | Legacy 仍是权威结果；新 Runtime 同时评估但不执行副作用、不写重复业务记录、只记录决策差异 |
| `runtime` | 新 Runtime 是权威结果 |
| `disabled` | 明确关闭能力，不允许静默当作 ALLOW |

## 4.4 谁负责共存期路由

只能由 `GovernanceGateway` / `RuntimeRouter` 负责。不能让 Web、MCP、SDK 或每个模块各自判断。

## 4.5 现有大模块的定位

`policy_engine.py`、`evaluator.py`、`self_healer.py` 等**不搬迁、不重写**。它们继续作为领域引擎：

```text
PolicyEngine / Evaluator / SelfHealer / ConflictDetector / CostTracker / PromptGuard
```

新 Runtime 通过 Adapter 调用它们：

```text
PromptGuardEvaluatorAdapter
PolicyEngineEvaluatorAdapter
ConflictEvaluatorAdapter
SelfHealingEvaluatorAdapter
```

Runtime 负责：上下文、调度、结果标准化、决策合并、Enforcement、Evidence。  
旧模块继续负责其领域计算。

> **Runtime 不是替代所有模块，而是控制这些模块什么时候运行、如何合并、是否执行。**

## 4.6 单写者原则（Shadow Mode 关键约束）

Shadow Mode 最大风险是重复副作用。必须区分：

| 操作类型 | 允许的调用方 |
|---------|------------|
| **Evaluate**（纯读取、纯计算） | Legacy + Runtime Shadow 均可 |
| **Mutate**（副作用写入） | 仅权威路径（Legacy 或 Runtime，不能同时） |

Shadow Mode 只允许 Runtime 调用纯 Evaluator：`estimate_budget_decision(snapshot)`。  
不能调用：`track()`、`set_budget()`、`audit.log()`、`self_heal()`。

## 4.7 迁移顺序（按风险从低到高）

```text
1. Prompt Guard       （纯读取判断，副作用最小）
2. Budget Preflight    （纯读取，只需估算）
3. Tool Policy         （纯匹配）
4. Conflict Decision   （纯检测）
5. Health / Anomaly    （少量写入）
6. Quality Gate        （涉及外部 Agent 调用）
7. Self-Healing        （副作用最多，最后迁移）
```

## 4.8 Legacy 删除条件

某项能力满足以下全部条件后，才删除旧直连路径：

- [ ] Runtime Mode 已运行至少一个完整版本
- [ ] Shadow 决策差异率低于 1%
- [ ] 7 天内没有触发 Legacy 回退
- [ ] 所有入口已通过 Gateway
- [ ] 仓库不存在外部直连 Import
- [ ] E2E 和回归测试通过
- [ ] 运维文档已更新

建议增加静态检查，禁止 Web/MCP 新代码中出现 `from ahy_governance.prompt_guard import get_guard`，只能从 Gateway 访问。

---

# 5. 版本路线（修订后）

| 版本 | 周期 | 目标 | 核心交付 |
|------|------|------|---------|
| **v0.10** | 10 周 | 控制闭环 MVP | Gateway + Context/Decision/Engine + Prompt Guard + Budget Preflight + BLOCK/REDACT（Generic + LangChain）+ 最小身份和 Workspace + 审计 Decision/Enforcement Result + Web/MCP/SDK 统一入口 |
| **v0.11** | 3–4 周 | 运行控制扩展 | THROTTLE + RETRY + ESCALATE + Tool Policy + Conflict Block + CrewAI 契约修复 + 审计链恢复 |
| **v0.12** | 4–6 周 | 恢复与质量闭环 | RecoveryActionExecutor + MODEL_FALLBACK + Checkpoint Resume + Recovery Verifier + Recovery Learner 闭环 + AgentRunner + Quality Gate CI 阻断 |
| **v1.0** | — | 生产就绪 | 达到全部 v1.0 发布标准后发布 |

---

# 6. 十周实施总览（v0.10 MVP）

| 周期 | 主目标 | 主要交付 |
|---|---|---|
| 第 0 周，2 天 | 冻结基线 | Tag 规范、状态矩阵、`xfail` 缺陷测试、Commit SHA 基线 |
| 第 1 周 | SDK 和事件契约 | `@track` 兼容、统一事件 Envelope |
| 第 2 周 | 身份与多租户 | JWT/API Key、WorkspaceContext、数据隔离 |
| **第 3 周** | **最小 Runtime 闭环** | Context + Decision + Engine（3 文件），接入 Prompt Guard + Budget Preflight（2 Evaluator） |
| **第 4 周** | **最小 Enforcement** | Generic BLOCK/REDACT + LangChain BLOCK/REDACT + EnforcementResult + 审计记录 |
| 第 5 周 | 审计、成本、健康正确性 | 持久化恢复、单位和周期修复、预算调用前预留 |
| 第 6–8 周 | 渐进迁移：按能力逐一切换 | Prompt Guard → Budget → Tool Policy → Conflict，每项走 Legacy→Shadow→Runtime |
| 第 9 周 | Web/MCP/SDK 收敛 | Gateway 统一入口、API 权限矩阵、Dashboard 修复 |
| 第 10 周 | 稳定化 | E2E、混沌测试、RC 发布 |

---

# 7. Phase 0：冻结基线与建立事实矩阵

**周期：2 天**

## 7.1 任务

### FND-01：冻结基线并规范 Tag

- 记录基线 Commit SHA：`6345978`
- 创建审计基线 Tag：`audit-baseline-2026-07-31`
- 创建改造分支：`refactor/governance-runtime`
- 禁止在主分支直接增加新能力
- 所有改造经 PR 合并

**Tag 规范（即日起执行）：**

| 类型 | 格式 | 示例 |
|------|------|------|
| 正式发行 | `v0.10.0`、`v0.10.1` | SemVer，包版本与 Tag 一致 |
| 功能里程碑 | `milestone/autoheal-diagnosis` | 记录阶段性能力节点 |
| 审计基线 | `audit-baseline-2026-07-31` | 改造前快照 |

以后计划基线一律写 Commit SHA，Tag 只作为辅助标识。

### FND-02：建立模块状态矩阵

新增：

```text
docs/status-matrix.md
```

每个模块必须标记：

- `WIRED`：已进入主运行链；
- `PARTIAL`：部分接线；
- `LIBRARY_ONLY`：只有独立 API；
- `METADATA_ONLY`：仅定义配置或策略；
- `STUB`：占位或不可用；
- `PLANNED`：仅设计。

### FND-03：为已知缺陷补 Characterization Tests

先写失败测试，**使用 `xfail(strict=True)` 标记**——不能直接把 main 打红：

```python
@pytest.mark.xfail(
    strict=True,
    reason="Known defect: runtime evaluator scores case.input as output",
)
def test_eval_scores_actual_agent_output():
    ...
```

修复完成后：
1. 移除 `xfail` 装饰器；
2. 测试必须通过；
3. `strict=True` 确保测试意外 XPASS 时 CI 提醒清理。

已知缺陷测试清单：

- README `@track(name=...)` 示例失败；
- `@track` 异常未触发 `on_error`；
- 健康延迟单位错误；
- OutputGuard 未加载策略时异常；
- `run_eval()` 把 input 当 output；
- Web WorkspaceContext 永远匿名；
- Audit 重启后链断裂；
- AGP 同名 Agent 跨 workspace 冲突；
- MCP Dashboard `float(summary_json)` 异常；
- CrewAI 延迟计时错误。

## 7.2 验收标准

- 已知缺陷全部有 `xfail(strict=True)` 自动化测试；
- 主分支没有新增未登记模块；
- 状态矩阵覆盖所有公开模块；
- README 能明确区分"已实现"和"规划中"；
- Tag 按新规范执行。

---

# 8. Phase 1：修复 SDK、事件契约和公开接口

**周期：第 1 周**

## 8.1 SDK-01：修复 `@track` API

推荐保留兼容层：

```python
@track(
    agent="my-agent",
    framework="langgraph",
    version="1.0.0",
    model="deepseek-chat",
)
```

兼容旧参数：

```python
@track(name="my-agent", ...)
```

处理规则：

- `name` 是 `agent` 的废弃别名；
- 同时传入时，`agent` 优先；
- 输出 DeprecationWarning；
- v1.0 移除旧别名。

## 8.2 SDK-02：异常必须进入治理管道

装饰器捕获异常后必须调用：

```python
pipeline.on_error(
    AgentErrorEvent(...)
)
```

但不能吞掉原异常。

标准流程：

```text
on_agent_start
    ↓
执行用户函数
    ├─ 成功 → on_agent_end
    └─ 失败 → on_error → on_agent_end(success=False) → 原异常继续抛出
```

## 8.3 EVT-01：建立统一 GovernanceEvent Envelope

建议新增：

```python
@dataclass
class GovernanceEvent:
    event_id: str
    event_type: str
    timestamp: str
    workspace_id: str
    agent_id: str
    agent_name: str
    session_id: str
    trace_id: str
    framework: str
    payload: dict
    schema_version: str = "1.0"
```

所有框架事件必须先转换为该 Envelope，再进入 GovernanceGateway。

## 8.4 EVT-02：补齐调用观测字段

调用记录至少包括：

- `started_at`
- `ended_at`
- `latency_ms`
- `input_length`
- `output_length`
- `tokens_in`
- `tokens_out`
- `success`
- `error_type`
- `tool_name`
- `model`

## 8.5 PKG-01：修复发行包内容

检查 `pyproject.toml` 中被排除的模块：

- `policy_engine`
- `compliance_reporter`
- `webhook_alerts`
- `interfaces`
- `migration`
- `scaffold`

处理方式二选一：

1. 开源能力：纳入正式包；
2. 企业保留能力：从 README 和 `__init__.py` 公共接口移除。

不得出现"源码仓库存在，但 PyPI 安装后缺失"的状态。

## 8.6 验收标准

- README 所有 Quick Start 可复制运行；
- Sync/Async `@track` 都能记录成功和失败事件；
- 所有事件包含统一身份字段；
- PyPI Dry Run 包含所有承诺的开源模块；
- SDK 契约测试通过。

---

# 9. Phase 2：统一身份认证和多租户隔离

**周期：第 2 周**

## 9.1 AUTH-01：合并两套认证模型

当前 `AuthManager` 和 `AccessManager` 应合并为统一 Identity Service。

建议领域模型：

```text
User
Workspace
WorkspaceMembership
Role
Permission
ApiKey
SessionToken
```

禁止继续维护：

- AuthManager 的用户级 API Key；
- AccessManager 的另一套内存 API Key。

## 9.2 AUTH-02：真实解析 WorkspaceContext

`resolve_workspace_context()` 必须支持：

```text
Authorization: Bearer <JWT>
Authorization: ApiKey <key>
X-Workspace-Id: <workspace>
```

验证流程：

1. 验证 Token 或 API Key；
2. 解析 user_id；
3. 检查用户是否属于 workspace；
4. 解析 role 和 permissions；
5. 写入 `request.state.workspace_ctx`；
6. 非公开 API 认证失败返回 401；
7. 权限不足返回 403。

## 9.3 AUTH-03：公开端点白名单

只允许：

- `/api/auth/register`
- `/api/auth/login`
- `/api/proxy/health`
- 静态资源

所有 `/demo` 写操作默认关闭：

```text
AHY_ENABLE_DEMO_ENDPOINTS=0
```

生产环境必须强制为 0。

## 9.4 TENANT-01：所有 Singleton 改为 Workspace Scoped

禁止：

```python
_global_tracker
_global_monitor
_global_auditor
```

推荐：

```python
container.for_workspace(workspace_id).cost_tracker
```

或者所有读写均直接使用数据库查询，不缓存跨租户状态。

## 9.5 TENANT-02：数据层约束

每个业务表：

- `workspace_id NOT NULL`
- 唯一键包含 workspace_id
- 所有查询强制 workspace 条件
- PostgreSQL 可选启用 RLS

例如：

```sql
UNIQUE(workspace_id, agent_id)
```

而不是全局 `agent_id PRIMARY KEY`。

## 9.6 验收标准

- 无认证访问受保护 API 返回 401；
- Viewer 无法执行写操作；
- 两个 workspace 同名 Agent 不冲突；
- 租户 A 不能读取租户 B 的 Cost/Audit/Health；
- 多租户隔离 E2E 测试 ≥ 20 个。

---

# 10. Phase 3：最小 Governance Runtime 闭环

**周期：第 3 周**

> **范围从原计划削减：** 7 文件 → 3 文件，7 Evaluator → 2 Evaluator。先建立闭环再扩展。

## 10.1 新增文件

只建三个文件：

```text
ahy_governance/runtime/
  context.py      — GovernanceContext dataclass
  decision.py     — GovernanceDecision dataclass + 决策合并
  engine.py       — GovernanceEngine：调度 Evaluator + 合并 Decision
```

**不建：** `container.py`（第 9 周统一）、`evaluator.py`（旧模块保留为领域引擎）、`enforcement.py`（第 4 周）、`evidence.py`（第 5 周）。

## 10.2 只接两个 Evaluator

### Prompt Guard Evaluator（通过 Adapter 调用旧 `prompt_guard.py`）

```python
class PromptGuardEvaluator:
    def evaluate(self, event: GovernanceEvent, context: GovernanceContext) -> list[GovernanceFinding]:
        # 调用旧模块 prompt_guard.sanitize()，包装为 GovernanceFinding
        ...
```

### Budget Preflight Evaluator（通过 Adapter 调用旧 `cost_tracker.py`）

```python
class BudgetPreflightEvaluator:
    def evaluate(self, event: GovernanceEvent, context: GovernanceContext) -> list[GovernanceFinding]:
        # 调用旧模块的估算方法（纯读取），不写成本记录
        ...
```

**其他 Evaluator（Tool Policy、Conflict、Health、Agent Level、Quality Gate）推迟到 v0.11+。**

## 10.3 核心数据结构

### GovernanceContext

```python
@dataclass
class GovernanceContext:
    workspace_id: str
    agent: AgentIdentity
    session_id: str
    trace_id: str
    phase: str
    event: GovernanceEvent
    budget: BudgetSnapshot
    health: HealthSnapshot
    policy_set: PolicySet
    prior_decisions: list
```

### GovernanceDecision

```python
@dataclass
class GovernanceDecision:
    decision_id: str
    action: str          # ALLOW | WARN | BLOCK | REDACT
    severity: str        # INFO | WARNING | CRITICAL
    phase: str           # pre_agent | pre_llm | pre_tool | post_output
    policy_ids: list[str]
    reasons: list[str]
    evidence: dict
    required_enforcement: dict
    created_at: str
```

v0.10 只支持四种动作：

```text
ALLOW
WARN
BLOCK
REDACT
```

其余动作（THROTTLE、RETRY、MODEL_FALLBACK、ESCALATE 等）保留在枚举中但执行器推迟到 v0.11+。

## 10.4 决策合并规则

优先级：

```text
BLOCK > REDACT > WARN > ALLOW
```

原则：

- 任何 CRITICAL BLOCK 不可被低优先级 ALLOW 覆盖；
- 多条 REDACT 必须可组合；
- 每个决定必须记录触发策略和证据；
- LLM Evaluator 失败时按安全策略降级（safe-default），不得静默放行高风险动作；
- 同一输入重放得到相同决策。

## 10.5 验收标准

- Prompt Guard 和 Budget Preflight 通过同一 Engine 调用；
- 不再由 Web/MCP 手工拼接不同模块；
- Decision 结果具有确定性；
- 规则决策 P95 < 20ms；
- 同一输入重放得到相同决策；
- 旧测试 100% 通过（Engine 不改变业务行为，仅作为新入口）。

---

# 11. Phase 4：最小强制执行

**周期：第 4 周**

> **范围从原计划削减：** 六种动作 → 两种动作（BLOCK + REDACT），三个框架 → 两个框架（Generic + LangChain）。CrewAI 保持观测模式。

## 11.1 ENF-01：定义 EnforcementAdapter

```python
class EnforcementAdapter(Protocol):
    def enforce(
        self,
        decision: GovernanceDecision,
        context: GovernanceContext,
    ) -> EnforcementResult:
        ...
```

## 11.2 ENF-02：v0.10 只实现两个动作

### BLOCK

- 不调用 Agent；
- 不调用 Tool；
- 返回结构化阻断原因。

### REDACT

- 返回实际脱敏后的 payload；
- 不只是返回"应脱敏"。

### 推迟到 v0.11+

- THROTTLE
- RETRY
- MODEL_FALLBACK
- ESCALATE
- ROLLBACK
- RESTART_AGENT

## 11.3 ENF-03：框架执行边界（v0.10 两个框架）

### LangChain

在以下回调执行治理：

- `on_chain_start`：Pre-Agent；
- `on_llm_start`：Pre-LLM；
- `on_tool_start`：Pre-Tool；
- `on_llm_end`：Mid/Post Output；
- `on_chain_error`：Recovery。

### Generic SDK

`@track` 负责 Agent 生命周期；另提供：

```python
guarded_tool()
guarded_llm_call()
guarded_agent()
```

### CrewAI（v0.10：观测模式）

- 修复计时（ADP-01：统一 run_id）；
- 通过契约测试（ADP-02）；
- **不实现 before-step 强制执行**（推迟到 v0.11）。

## 11.4 ENF-04：执行验证

每个动作都产生：

```python
@dataclass
class EnforcementResult:
    decision_id: str
    attempted: bool
    succeeded: bool
    applied_action: str
    before: dict
    after: dict
    verification: dict
    error: str | None
```

## 11.5 验收标准

- BLOCK 测试证明目标函数没有执行；
- REDACT 测试证明敏感数据已被替换；
- LangChain + Generic SDK 均通过 Enforcement 契约测试；
- 所有治理决定都有 EnforcementResult；
- 审计记录包含 Decision + EnforcementResult；
- CrewAI 契约测试通过（观测模式）。

---

# 12. Phase 5：修复审计、成本和健康正确性

**周期：第 5 周**

（本节内容与原始计划基本一致，已精简为关键要点。）

## 12.1 AUD-01：审计链持久化恢复

AuditReporter 初始化时必须：

1. 按 workspace 读取最后一条记录；
2. 恢复 index 和 root_hash；
3. 新事件连接到已有链；
4. 验证整个持久化链；
5. 检测断链、重复 index 和跨 workspace 串链。

链键：`workspace_id + audit_stream`

## 12.2 AUD-02：审计不能轻易宣称合规

修改术语为 `SOC2 Evidence Export` / `ISO27001 Evidence Mapping`。  
不能直接返回 `status = compliant` 除非有明确控制证据。

## 12.3 COST-01：预算按 workspace 和周期运行

实现 `daily` / `monthly` / `rolling_30d` / `total` 预算周期。  
每条预算包含：period_start、period_end、current_usd、reserved_usd、reset_policy、hard_limit、soft_limit。

## 12.4 COST-02：调用前预算预留

```text
估算调用成本 → 预留预算 → 允许执行 → 实际记账 → 释放或补差额
```

避免调用完成后才发现超预算。

## 12.5 HLT-01：修复时间单位

所有内部单位统一为 `latency_ms`、`heartbeat_age_seconds`、`timeout_seconds`。  
阈值显式命名：`DEGRADED_P95_LATENCY_MS = 60_000`、`UNHEALTHY_P95_LATENCY_MS = 300_000`。

## 12.6 ANM-01：修复异常检测

- 每次调用记录真实 timestamp；
- 60 秒窗口按 timestamp 统计；
- `output_length` 进入标准事件；
- Token Spike 按时间排序；
- 数据不足时返回 `INSUFFICIENT_DATA`。

## 12.7 验收标准

- 审计链重启后继续连接；
- 两个 workspace 审计链完全独立；
- 月预算自动重置；
- 超预算 Agent 在调用前被阻止；
- 500ms 正常请求不会被判断为 500 秒；
- 异常检测使用真实时间窗口。

---

# 13. Phase 6：现有自愈决策链的执行与验证补全

**周期：第 6–8 周（与渐进迁移并行）**

> **关键修正：** 不是从零建设 Self-Healing。当前 SelfHealer（526 行）已有完整决策链——从故障识别到 RecoveryAction 到 RecoveryLedger——但 `_finalize()` 写入 `ATTEMPTED` 后直接返回，没有真正执行动作。

## 13.1 已有，直接复用

| 模块 | 现状 |
|------|------|
| `SelfHealer` | 故障识别 → 规则匹配 → LLM 诊断 → RecoveryAction 选择 |
| `RuleEngine` | 规则定义和匹配 |
| `LLMDoctor` | DeepSeek 诊断，生成结构化 RecoveryAction |
| `RecoveryLedger` | 恢复记录持久化 |
| `RecoveryLearner` | 从 ledger 学习候选规则 |
| `CheckpointStore` | 上下文保存和恢复 |
| `RecoveryAction` | 结构化恢复动作定义 |
| `HealResult` | 恢复结果数据结构 |
| 默认恢复规则 | `recovery_rules.py` 中的规则库 |
| MCP/Web 触发入口 | `ahy_self_heal()`、`ahy_auto_heal_check()` |

## 13.2 真正缺失，必须新增

### REC-01：RecoveryActionExecutor

```python
class RecoveryActionExecutor:
    def execute(
        self,
        action: RecoveryAction,
        target: AgentTarget,
        context: dict,
    ) -> RecoveryExecution:
        ...
```

### REC-02：各动作的具体 Adapter

- Retry Adapter
- Context Truncate Adapter
- Model Fallback Adapter
- Restart Agent Adapter（高风险，需人工审批）
- Rollback Adapter（高风险，需人工审批）

### REC-03：执行幂等控制

每个 Execution 携带幂等键，防止重复执行。

### REC-04：执行超时和次数限制

RETRY 最大次数 + 指数退避 + 失败后升级。

### REC-05：动作分级

| 风险级别 | 动作 | 审批要求 |
|---------|------|---------|
| 低风险 | RETRY、CONTEXT_TRUNCATE、OUTPUT_VALIDATE、MODEL_FALLBACK 到批准模型 | 自动执行 |
| 中风险 | CIRCUIT_BREAK、重置 Session、重新触发上游 Agent | 策略批准后执行 |
| 高风险 | ROLLBACK 外部状态、RESTART_AGENT、文件/数据库恢复、财务/通信补偿 | 必须人工批准 |

### REC-06：动作完成后的 Verifier

```text
执行动作 → 检查是否成功 → 检查输出质量门 → 写 SUCCEEDED 或 FAILED
```

禁止把 `ATTEMPTED` 记成成功。

### REC-07：真正的 Checkpoint Resume Adapter

Checkpoint 恢复需要：状态版本 + Schema + Agent runtime locator + 恢复适配器 + 幂等键 + 恢复验证。  
当前只返回 `restore_context` 不够。

### REC-08：恢复后的观察窗口

成功后不立即关闭事件——在观察窗口内无复发才确认为恢复。

### REC-09：失败补偿与人工审批

高风险动作没有人工批准时不能执行；提供结构化审批流程而非"请人工处理"的自然语言提示。

## 13.3 REC-10：Recovery Learner 闭环

只学习：

- 动作真正执行；
- Verifier 判定成功；
- 后续观察窗口无复发；
- 人工未标记错误恢复。

学习规则默认 Disabled，人工审核后启用。

## 13.4 REC-11：修复并发问题

- 不得为单次请求修改全局 `self.level = level_override`——直接把 effective_level 作为局部参数传递；
- 规则 cooldown 键改为 `workspace_id + agent_id + rule_id`。

## 13.5 验收标准

- RETRY 真实执行并验证；
- MODEL_FALLBACK 真实切换模型；
- 失败动作不会写 SUCCEEDED；
- Recovery Learner 可从真实成功记录生成候选规则；
- 高风险动作没有人工批准时不能执行；
- 执行前检查幂等键，不重复执行已完成动作。

---

# 14. Phase 7：评测与质量门修复

**周期：推迟到 v0.12**

> v0.10 仅修复 `run_eval()` 评分对象错误（作为 P0 修复纳入 Phase 1）。完整的 AgentRunner + Quality Gate CI 阻断推迟到 v0.12。

---

# 15. Phase 8：AGP、注册中心和适配器修复

**周期：第 8 周（Bug 修复部分提前到 Phase 1）**

## 15.1 AGP-01：修复编码损坏

清理 `agent_registry.py` 中乱码，增加 CI：UTF-8 BOM 检查、U+FFFD 检查、常见 mojibake 检查。

## 15.2 AGP-02：重新定义 Agent Identity

```text
agent_id = UUID
workspace_id + external_agent_key UNIQUE
```

manifest 中可以显式提供稳定 Agent ID，不再只由名称和框架推导。

## 15.3 AGP-03：能力声明与验证分离

必须区分 `declared_capabilities` / `verified_capabilities` / `effective_capabilities`。  
Agent 自称可以写数据库，不等于平台已经验证。

## 15.4 ADP-01：修复 CrewAI 计时

使用统一 run_id，而不是混用 `id(agent)` 和 `id(step)`。

## 15.5 ADP-02：适配器契约测试

建立框架无关测试套件（Agent Start → LLM Start → LLM End → Tool Start → Tool End → Agent End → Agent Error），每个适配器必须通过同一组事件契约。

## 15.6 验收标准

- 跨 workspace 同名 Agent 可共存；
- AGP Manifest Schema 可版本迁移；
- 声明能力和验证能力分开；
- LangChain/CrewAI/Generic 事件行为一致；
- README 准确描述发现能力。

---

# 16. Phase 9：收敛 Web、MCP 和 SDK

**周期：第 9 周**

## 16.1 PLT-01：GovernanceGateway 统一入口

Web、MCP、SDK 不再各自初始化单例或直连模块。

```text
Web ─┐
MCP ─┼─→ GovernanceGateway
SDK ─┘
```

Gateway 装配：Database、Identity Service、Governance Engine、Evaluators（Adapter 包装）、Enforcers、Audit、Recovery、Registry、Config。

## 16.2 MCP-01：自动加载真实能力

MCP 启动时必须：加载默认策略、绑定数据库、注册 Action Handler、验证 Full Auto 配置、输出能力状态。

新增 `ahy_get_capability_status`，返回每个模块：enabled、wired、enforcement_supported、verifier_supported。

## 16.3 MCP-02：修复 Dashboard JSON 解析

```python
# 错误
float(summary_json)

# 正确
summary = json.loads(summary_json)
latest_score = summary.get("avg_score")
```

## 16.4 WEB-01：API 权限矩阵

| API | Viewer | Operator | Admin |
|---|---:|---:|---:|
| 读取 Health | ✓ | ✓ | ✓ |
| 修改预算 | × | ✓ | ✓ |
| 执行自愈 | × | 条件允许 | ✓ |
| 管理策略 | × | × | ✓ |
| 导出审计 | × | ✓ | ✓ |

## 16.5 WEB-02：修复探针审计 + 移除大范围异常吞噬

- 添加真实事件：`AGENT_HEARTBEAT`、`AGENT_PROBE_FAILED`、`AGENT_PROBE_RECOVERED`；
- 所有裸 `except Exception: pass` 改为：记录结构化日志 → 返回降级状态 → 计入健康指标 → 严重错误进入审计。

## 16.6 验收标准

- Web/MCP/SDK 通过同一 Gateway；
- MCP 默认策略非空；
- Dashboard 有评测记录时不报错；
- 所有业务 API 有权限测试；
- 后台探针错误可观测。

---

# 17. Phase 10：稳定化和发布候选

**周期：第 10 周**

## 17.1 测试分层

### Unit Tests

每个 Evaluator、每个 Enforcer、每个 Verifier、决策优先级、Workspace 过滤、审计 Hash。

### Contract Tests

SDK、LangChain、CrewAI、MCP、Web API、AGP Manifest。

### Integration Tests

Agent → Gateway → Engine → Decision → Enforcement → Audit（含 Budget Block、Prompt Redact、Conflict Block、Self-Heal Retry、Quality Gate Fail）。

### Chaos Tests

DB 断开、LLM Judge 超时、Agent 长时间无响应、重复事件、审计记录损坏、Recovery Action 失败、MCP 并发请求。

### Security Tests

JWT 伪造、API Key 越权、Workspace 穿透、Prompt Injection、PII 泄漏、Demo Endpoint 暴露、SSRF、速率限制绕过。

## 17.2 发布 Gate

发布 RC 前必须满足：

```text
ruff               PASS
format             PASS
bandit             PASS
unit tests         PASS
integration tests  PASS
tenant isolation   PASS
security tests     PASS
migration tests    PASS
coverage >= 85%
P0 bugs = 0
P1 bugs <= 3 且均有停止条件
```

## 17.3 文档重写

README 使用能力状态表：

| 能力 | 状态 | 强制执行 | 持久化 |
|---|---|---|---|
| 成本追踪 | Stable | 是 | 是 |
| Prompt Guard | Stable | 是 | 是 |
| 自愈重试 | Beta | 是 | 是 |
| 自动回滚 | Planned | 否 | 否 |

## 17.4 验收标准

- 全部发布 Gate 通过；
- 从空环境 15 分钟内完成安装和运行；
- Quick Start 可复制；
- 生产配置与 Demo 配置完全分离；
- 发布 `v0.10.0-rc.1`。

---

# 18. 可选 Phase 11–14：分布式控制面

只有在 v0.10 主线完成后再做。

## 第 11 周：Durable Event Bus

PostgreSQL Outbox + Worker 消费 + 至少一次投递 + 幂等去重 + Dead Letter Queue。

## 第 12 周：OpenTelemetry

Trace ID 贯穿 Agent、Tool、Model、Governance；Metrics；Logs；Decision Span；Enforcement Span。

## 第 13 周：分布式 Policy Decision Point

策略版本、灰度发布、Workspace Policy Bundle、规则缓存、策略回滚、决策签名。

## 第 14 周：Agent Sidecar / Gateway

支持 SDK Embedded 和 Agent Sidecar/Gateway 两种接入方式。Sidecar 提供 Pre-Tool 阻断、网络访问限制、成本预算、统一审计、模型路由、输出脱敏。

---

# 19. 任务优先级清单（v0.10 范围）

## P0：必须立即完成（Phase 0–2）

1. README 与 `@track` API 一致
2. `@track` 异常触发 `on_error`
3. 修复健康延迟单位
4. 修复异常检测时间窗口
5. 修复 `run_eval()` 评分对象
6. OutputGuard 默认加载策略
7. 修复 OutputGuard 默认参数异常
8. 合并认证与 WorkspaceContext
9. 非公开 API 真实认证
10. 修复 PyPI 模块排除
11. 审计链跨重启恢复
12. 修复 AGP 乱码
13. 修复 AGP 多租户主键
14. 修复 MCP Dashboard JSON 解析
15. 修复 Web 探针不存在事件
16. 修复 CrewAI 计时

## P1：v0.10 Must Have（控制闭环 MVP）

1. GovernanceGateway（唯一路由层）
2. GovernanceContext + GovernanceDecision + GovernanceEngine（3 文件）
3. Prompt Guard Evaluator（通过 Adapter 调用旧模块）
4. Budget Preflight Evaluator（通过 Adapter 调用旧模块）
5. Generic SDK：BLOCK + REDACT 执行器
6. LangChain：BLOCK + REDACT 执行器
7. EnforcementResult + 审计记录
8. Web/MCP/SDK 通过 Gateway 统一入口
9. 身份和 Workspace 最小闭环
10. **main 始终全绿**

## P2：v0.10 Should Have（有余力）

1. THROTTLE 执行器
2. 简单 RETRY 执行器（Generic）
3. Tool Allowlist/Denylist Evaluator
4. Conflict Critical Block Evaluator
5. CrewAI 契约测试通过（观测模式）
6. 审计链重启恢复

## P3：推迟到 v0.11+

1. RecoveryActionExecutor + 完整自愈执行
2. MODEL_FALLBACK / ROLLBACK / RESTART_AGENT
3. 完整 Checkpoint Resume
4. Recovery Learner 真实闭环
5. CrewAI Before-Step 强制执行
6. Quality Gate 真实 AgentRunner + CI 阻断
7. 全部七类 Evaluator
8. 分布式事件总线
9. Sidecar/Gateway

---

# 20. 风险与停止条件

| 风险 | 停止条件 | 处置 |
|---|---|---|
| 新 Runtime 破坏 SDK 兼容性 | 旧示例失败率 > 5% | 增加兼容层和双版本测试 |
| Policy 误拦截正常任务 | BLOCK 误报率 > 2% | 降为 WARN，收集证据后再升格 |
| 自愈形成循环 | 同 Agent 5 分钟内恢复 > 3 次 | 自动熔断并升级人工 |
| 多租户数据泄漏 | 任一隔离测试失败 | 停止发布，视为安全 P0 |
| LLM Judge 成本过高 | 评测成本超过 Agent 成本 20% | 缓存、抽样、规则前置 |
| 审计链断裂 | 任一 workspace 校验失败 | 停止写入并触发安全告警 |
| 迁移失败 | 数据丢失或回滚不可用 | 停止部署并恢复旧版本 |
| Dashboard 与后端状态不一致 | 差异 > 1 个采集周期 | 禁止展示"实时"标签 |
| **Shadow Mode 重复副作用** | **同一调用两个路径各写一次** | **立即停止 Shadow，单写者审计验证** |
| **CI 长期红色** | **连续 2 个 PR 合入后 CI 不绿** | **停止合并，修复后再继续** |

---

# 21. 每周交付检查表

每周结束必须完成：

- [ ] 本周 PR 已合并且 **CI 全绿**；
- [ ] 状态矩阵已更新；
- [ ] 新模块已标记 WIRED/PARTIAL/STUB；
- [ ] 新增行为有自动化测试；
- [ ] 文档与真实 API 一致；
- [ ] 没有新增裸 `except Exception: pass`；
- [ ] 没有新增全局跨租户 Singleton；
- [ ] 没有把建议动作描述成已执行；
- [ ] 没有把 Attempted 记录成 Succeeded；
- [ ] 没有两套路径同时写入同一副作用（单写者原则）；
- [ ] **所有 `xfail` 测试：新增的严格（strict=True），修复后移除装饰器**；
- [ ] 下一周依赖明确。

---

# 22. v1.0 发布标准

只有以下条件全部满足，才建议发布 v1.0：

1. 三种接入方式至少两种稳定：Generic SDK、LangChain、CrewAI。
2. GovernanceGateway 是唯一入口，不存在外部直连 Import。
3. BLOCK/REDACT/THROTTLE/RETRY 有真实执行器。
4. 所有自愈成功均经过 Verifier。
5. Quality Gate 评估真实输出并可阻断 CI。
6. JWT/API Key/Workspace/RBAC 形成统一身份链。
7. 审计链可跨重启、按 workspace 校验。
8. 预算在调用前执行。
9. 生产环境无公开 Demo 写接口。
10. E2E、Chaos、Security、Migration 全通过。
11. 文档不包含超出代码能力的宣传。
12. 至少完成一次真实多 Agent 项目接入验证。

---

# 23. 修订后的 PR 序列（Additive → Shadow → Runtime）

> **核心原则：** 每次 PR 不改变业务行为，只增加新路径；main 始终全绿。

```text
=== Phase 0: 基线冻结 ===
PR-01  docs: add capability status matrix
PR-02  test: add known-defect xfail characterization suite（strict=True）

=== Phase 1: P0 修复 ===
PR-03  fix: align track decorator API and error events
PR-04  fix: health latency units and call timestamps
PR-05  fix: evaluator scores actual outputs（移除 run_eval 的 xfail）
PR-06  fix: initialize output guard policies safely
PR-07  fix: unify web auth and workspace context
PR-08  fix: persist and restore audit chains per workspace

=== Phase 3–4: 最小 Runtime（Additive，零行为变更） ===
PR-09  refactor: add GovernanceContext + GovernanceDecision + GovernanceGateway
       （Gateway 内部完全委托 Legacy，旧测试 100% 通过）
PR-10  refactor: add GovernanceEngine with PromptGuard + BudgetPreflight evaluator adapters
       （仅新增文件 + 测试，不改变旧调用路径）

=== Phase 4: 入口切到 Gateway（仍委托 Legacy） ===
PR-11  refactor: route Web/MCP/SDK through GovernanceGateway
       （Gateway 仍为代理层，所有决策走 Legacy）

=== Phase 9: 按能力渐进切换 ===
PR-12  feat: Prompt Guard Shadow Mode
       （Legacy 权威，Runtime 同时评估，只记录差异不执行）
PR-13  feat: Prompt Guard Runtime Mode
       （Runtime 接管 BLOCK/REDACT，Legacy 保留为回退）
PR-14  feat: Budget Preflight Shadow Mode
       （只评估不重复记账）
PR-15  feat: Budget Preflight Runtime Mode
       （Runtime 接管调用前预算判断，旧 CostTracker 仍负责实际记录）

=== 稳定化 ===
PR-16  test: add multi-tenant and governance E2E suite
PR-17  release: v0.10.0-rc.1 governance control loop MVP
```

---

# 24. 最终产品架构定位

改造完成后，产品应形成以下双层体系：

```text
Ahy Governance
多 Agent 治理控制平面
身份、策略、预算、冲突、审计、健康、自愈
                   │
                   ▼
Orcana Runtime
单 Agent 可靠执行内核
规划、变更影响、工具策略、证据、完成门控
                   │
                   ▼
代码仓库、企业 API、数据库、ERP/MES、外部工具
```

建议最终产品描述：

> **Ahy Governance 是面向多 Agent 系统的开源治理控制面，通过统一事件、策略决策、强制执行、验证证据和审计链，让 Agent 行为可观察、可约束、可恢复、可追溯。**

核心标语：

> **让每个 Agent 的行为，都有规则、有边界、有证据。**
