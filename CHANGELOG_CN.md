# 更新日志

本文件记录了 Ahy Governance 的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

## [0.10.0] — 2026-08-01

治理控制闭环 MVP — 收口 Phase 稳定化。

### 新增
- **治理运行时核心** — `GovernanceContext` / `GovernanceDecision` / `GovernanceEngine`，合并语义 BLOCK > REDACT > WARN > ALLOW
- **GovernanceGateway** — Web / MCP / SDK 统一路由层，四态路由（legacy / shadow / runtime / disabled）
- **Prompt Guard Shadow → Runtime** — Runtime 评估器权威裁决 + Legacy 回退（`legacy_fallback_count`）；Shadow 账本记录迁移期差异
- **Budget Preflight Shadow → Runtime** — 纯读预算预检（绝不重复记账），返回 `BudgetPreflightResult`；旧 CostTracker 仍负责记录
- **多租户隔离 E2E** — 存储按 `workspace_id` 隔离、复合主键、中间件上下文解析（X-Workspace-Id / ApiKey / 匿名）、RBAC 三级强制
- **治理主链 E2E** — 51 个真实场景：Web / MCP / SDK → Gateway → Engine → legacy
- 恢复学习引擎 — 从恢复账本中自动学习新的自愈规则
- DeepSeek LLMDoctor 集成 — LLM 辅助的事故诊断
- 自动触发自愈 + 检查点/恢复上下文

### 变更
- Web / MCP / SDK 的 guard + 成本调用统一经 GovernanceGateway
- 测试套件：930 → 1140 全部通过（多租户 24 + 治理主链 51）

### 修复
- **P0 跨租户数据泄漏** — `PUBLIC_API_*` 常量是字符串（缺尾逗号），导致所有 `/api/*` 路径恒为 public；workspace 上下文从未解析
- **P0 PII 死代码** — Runtime 模式下 Prompt Guard REDACT 分支永不触发（PII 改用 `redaction_count` 检测）

## [0.9.0] — 2026-05-31

### 新增
- **MCP 服务** — 通过 FastMCP 提供 18 个治理工具，支持 stdio + SSE 双模式，兼容 Claude Code、Cursor 等 MCP 客户端
- **自愈引擎（3 级）** — 规则恢复 → LLM 诊断 → 全自动闭环恢复
- **`@track` 装饰器** — 一行代码集成：`@track(name="agent", framework="langgraph")` 即可获得成本追踪、健康监控、审计日志、自动注册
- **Agent 等级评估** — Level 0-5 成熟度评估及等级治理建议
- **异常检测器** — token 用量尖峰检测、重复调用检测、内存耗尽监控，自动触发自愈
- **SDK 装饰器** — 支持同步/异步，提供 CrewAI 和 LangChain 适配器
- **质量门** — 数据集 + 评分器评估，通过/失败阈值，CI/CD 集成
- **AGP 发现** — Agent 清单扫描 + 进程/端口回退发现，自动识别 10 种框架
- 安全加固：PII 脱敏、Prompt 注入防御（13 种模式）、18 条护栏策略

### 变更
- Dashboard：7 面板深色主题，自动刷新，RBAC 工作空间管理
- CI/CD：Ruff 代码检查、Bandit 安全扫描、80% 覆盖率门槛
- 测试覆盖率：74% → 81%（新增 141 个测试）

### 修复
- MCP 冲突检测字典适配，兼容嵌套 Agent 输出
- CostEntry.to_dict() 现在正确包含 warning 字段
- MCP 工具：数据库注入加固 + 未知模型优雅处理

## [0.8.0] — 2026-05-07

### 新增
- **Web Dashboard** — 7 个面板：总览、健康、成本、冲突、审计、内存、安全
- **API 服务** — FastAPI 后端，为全部模块提供 REST 接口
- **CI/CD 流水线** — GitHub Actions：测试、Lint、发布
- Docker Compose 部署，Nginx 反向代理

## [0.7.0] — 2026-05-08

### 新增
- **PyPI 发布** — `pip install ahy-governance[web]`
- **审计报告器** — SHA-256 哈希链，SOC2/ISO27001 合规导出
- **成本追踪器** — 22 种模型定价，预算熔断，成本优化建议
- **冲突检测器** — 5 种冲突类型：事实、格式、依赖、作用域、置信度
- **健康监控器** — 心跳检测，P50-P99 延迟，错误率
- **认证与 RBAC** — 邮箱/密码 + JWT，3 级角色，API Key 全生命周期管理
- SQLite 持久化，支持 SQLite/PostgreSQL 双模式

## [0.1.0] — 2026-05-01

### 新增
- 核心治理库初始版本
- 多 Agent 编排基础能力
- 基础可观测性钩子

[未发布]: https://github.com/Leo-Ayh-Oday/ahy-governance/compare/v0.10.0...HEAD
[0.10.0]: https://github.com/Leo-Ayh-Oday/ahy-governance/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/Leo-Ayh-Oday/ahy-governance/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/Leo-Ayh-Oday/ahy-governance/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/Leo-Ayh-Oday/ahy-governance/compare/v0.1.0...v0.7.0
[0.1.0]: https://github.com/Leo-Ayh-Oday/ahy-governance/releases/tag/v0.1.0
