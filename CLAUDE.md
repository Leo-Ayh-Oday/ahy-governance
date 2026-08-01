# Ahy Governance
多 Agent 治理平台 — 冲突检测、成本追踪、审计合规、自愈恢复。面向 5+ Agent 的生产团队。

## Tech Stack
- 后端: Python 3.10+ / FastAPI + FastMCP / structlog
- 数据库: SQLite (本地) / PostgreSQL (生产, psycopg2 同步)
- 缓存: Redis (仅共享状态——预算熔断、心跳，不用作通用缓存)
- 部署: `pip install ahy-governance[web]` → `ahy-dashboard` (localhost:8081)
- 测试: pytest 790+ tests, ruff (E/F/W/I/N/UP/B/SIM), line-length=100

## Project Structure
```
ahy-governance/
├── ahy_governance/       # 核心库 (14 模块)
│   ├── conflict_detector.py  # 5 种冲突类型 (FACT/FORMAT/DEPENDENCY/SCOPE/CONFIDENCE)
│   ├── cost_tracker.py       # 预算追踪 + 熔断器
│   ├── audit_logger.py       # SHA-256 哈希链防篡改审计
│   ├── self_healer.py        # 3 级自愈 (rule → LLM → full-auto)
│   ├── policy_engine.py      # Agent L0-L5 分级 + 15 risk classes
│   ├── prompt_guard.py       # 注入检测 + PII 脱敏
│   ├── mcp_server.py         # 18 MCP tools, stdio transport
│   └── adapters/             # CrewAI, LangChain 适配器
├── web/                  # FastAPI 仪表板 + 静态前端
├── tests/                # pytest, test_*.py
└── docs/                 # 适配器计划、教程截图
```

## Architecture Decisions (from .wolf/cerebrum.md)
- PG 后端用同步 psycopg2 而非 async asyncpg — 避免大规模重构，保持与 SQLite 后端接口一致 (2026-05-17)
- Redis 仅用于多实例间共享状态（预算、心跳），不作为通用缓存 — 先解决真正的痛点 (2026-05-17)
- FastMCP 单文件 mcp_server.py + stdio transport — 从 Python 库升级为 MCP 基础设施 (2026-05-31)
- 微服务/K8s/ClickHouse/Kafka 暂缓 — 当前阶段 (v0.9.1, 0 付费客户) 过度设计 (2026-05-17)

## Domain Rules
- 不要信任 Agent 自报的成功报告 — Agent 会声称"所有测试通过"实际 89% 失败。必须有程序化验证管道，不能依赖 Agent 自我评估
- 单个 hallucination（如编造 ID）会传播到下游 Agent 成为 ground truth — Agent 之间传递的标识符必须由确定性代码注入，不能让模型自己生成
- 多个 Agent 共享同一模型时存在"单一栽培崩溃"风险 — 对相同输入的关联漏洞。生产环境至少确保关键决策 Agent 使用不同模型

## Conventions
- 导入顺序: `__future__` → stdlib → 三方 → `ahy_governance`，ruff isort 自动排序
- 测试: `tests/test_*.py`, Windows 用 `py` 启动器不是 `python`
- MCP 工具函数在 mcp_server.py 中用本地 import 调用 — 测试 patch 源模块不要 patch mcp_server
- AuditEventType 枚举值小写 (`agent_start`), Role 枚举 ADMIN/OPERATOR/VIEWER, Alert 用 `body` 和 `severity`

## History (git scars)
- `self_heal()` 曾直接修改 singleton 的 level，导致 MCP 多租户间泄漏 — 改为 `level_override` 参数传递 (git: a68202c)
- MCP 工具接收 JSON dict，但 `check_conflicts()` 期望 `.output` 属性 — 必须用 SimpleNamespace 包装 (git: cde25b5)
- MCP tools 忘记调用 `_ensure_db()` 导致 DB 未初始化；未知模型名直接 KeyError 崩溃 — 必须初始化 DB + unknown model 用默认定价 + warning (git: a28ac91)
- `get_engine` 是旧导入名，实际函数是 `get_policy_engine` — `__init__.py` 导出名需与函数名一致 (.wolf cerebrum 2026-05-31)
