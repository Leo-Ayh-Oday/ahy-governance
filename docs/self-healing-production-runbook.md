# Self-Healing Agent 生产运行说明

本文档用于把 Self-Healing Agent 从“模块已实现”固定成可审计、可回滚、可交接的生产流程。

## 核心闭环

生产链路应按以下顺序运行：

1. `anomaly_detector` 或 `health_monitor` 发现异常。
2. 系统读取对应 Agent 的最新 checkpoint。
3. `self_healer` 根据异常类型、错误信息和 checkpoint 上下文选择恢复动作。
4. 恢复结果写入 `recovery_ledger`。
5. API/MCP 返回 `restore_context`，用于让 Agent 知道自己应从哪里继续。

关键效果：

- 异常不再只是被报告，可以进入受控的自动修复入口。
- 修复后不会丢失执行现场，返回结果包含 session、step、checkpoint id 和 state。
- 每次恢复尝试都有 ledger 记录，便于审计和复盘。

## 默认安全策略

自动修复默认关闭。任何生产环境都不应默认启用 full-auto。

Web 自动修复入口：

```powershell
$env:AHY_WEB_FULL_AUTO = "1"
```

MCP 自动修复入口：

```powershell
$env:AHY_MCP_FULL_AUTO = "1"
```

通用开关：

```powershell
$env:AHY_FULL_AUTO = "1"
```

推荐策略：

- 本地开发：可以短时打开 full-auto 做验证。
- 预生产：只允许明确的测试 workspace 打开 full-auto。
- 生产：默认关闭，只有低风险、可回滚、已审计的 workspace 才打开。

## Checkpoint 保存要求

Agent 执行关键步骤前后应保存 checkpoint。最低字段要求：

- `agent_name`
- `session_id`
- `state`
- `step`
- `workspace_id`

Python 示例：

```python
from ahy_governance import save_checkpoint

save_checkpoint(
    agent_name="Planner",
    session_id="sess-47",
    state={"step": 47, "task": "continue current plan"},
    step="step-47",
    workspace_id="default",
)
```

恢复时返回的 `restore_context` 会包含：

```json
{
  "agent_name": "Planner",
  "session_id": "sess-47",
  "checkpoint_id": 1,
  "step": "step-47",
  "created_at": "2026-06-02T00:00:00+00:00",
  "state": {
    "step": 47,
    "task": "continue current plan"
  }
}
```

## Web 入口

只读异常扫描：

```http
GET /api/anomalies/scan
```

自动扫描并修复：

```http
POST /api/anomalies/scan-and-heal
```

未开启 `AHY_WEB_FULL_AUTO=1` 或 `AHY_FULL_AUTO=1` 时，自动修复接口必须返回 `403`。

## MCP 入口

只读异常扫描：

```text
ahy_detect_anomalies
```

自动扫描并修复：

```text
ahy_detect_and_heal_anomalies(workspace_id="")
```

健康自愈检查：

```text
ahy_auto_heal_check(workspace_id="")
```

未开启 `AHY_MCP_FULL_AUTO=1` 时，自动修复工具必须只返回 disabled 错误，不应调用 healer。

## PostgreSQL 验证清单

生产库需要具备以下表：

- `recovery_ledger`
- `recovery_rules`
- `agent_checkpoints`

真实 PG 烟测至少覆盖：

1. `create_database(DATABASE_URL)` 可以建表。
2. checkpoint 可以写入并读取。
3. `self_heal()` 可以从 checkpoint 生成 `restore_context`。
4. `anomaly_detector.scan_and_heal()` 可以触发 healer。
5. `recovery_ledger` 有对应记录。

本地验证结果示例：

```json
{
  "backend": "postgres",
  "checkpoint_id": 1,
  "restore_context_step": "step-47",
  "ledger_rows_planner": 1,
  "anomaly_heal_results": 1,
  "worker_ledger_rows": 1,
  "healing_status": "attempted"
}
```

## 审计与人工介入

以下情况必须人工介入：

- 未命中规则且没有可信历史恢复记录。
- LLM 建议高风险动作，例如重启 Agent、切换权限、修改凭证。
- 同一 Agent 短时间重复触发恢复。
- checkpoint 缺失或 `restore_context` 为空。
- ledger 记录显示恢复失败或状态持续恶化。

排查顺序：

1. 查看异常类型和 error message。
2. 查看最新 checkpoint 是否存在。
3. 查看 `restore_context` 是否包含正确 step 和 state。
4. 查看 `recovery_ledger` 的 action、status、diagnosed_by、confidence。
5. 决定继续自动恢复、降级到人工，或暂停该 workspace 的 full-auto。

## 发布前检查

发布前至少运行：

```powershell
py -m pytest -q
cmd /c npm run lint
py -m build --wheel
```

如要验证 PostgreSQL：

```powershell
py -m pip install "ahy-governance[postgres]"
$env:DATABASE_URL = "postgresql://ahy:password@localhost:5432/ahy_governance"
py -m pytest tests\test_storage.py -q
```

提交时应包含：

- `ahy_governance/anomaly_detector.py`
- `ahy_governance/health_monitor.py`
- `ahy_governance/self_healer.py`
- `ahy_governance/storage_pg.py`
- `ahy_governance/application/`
- `web/server.py`
- 前端自愈闭环相关文件
- `tests/`
- `docs/self-healing-production-runbook.md`

不应提交：

- `.coverage`
- `*.db`
- `build/`
- `dist/`
- `__pycache__/`
