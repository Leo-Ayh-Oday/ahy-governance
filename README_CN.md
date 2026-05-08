# Ahy Governance

**企业级 AI Agent 治理平台。冲突检测 · 成本追踪 · 审计日志 · 合规报告 — 7 模块，312 测试，开源 MIT。**

[![Tests](https://img.shields.io/badge/tests-312%20passed-green)](https://github.com/Leo-Ayh-Oday/ahy-governance/actions)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-purple)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.7.0-orange)](https://pypi.org/project/ahy-governance/)

企业上线 AI Agent 之后，技术负责人最怕五件事，Ahy Governance 全解决了：

1. **Agent 之间互相矛盾** → 5 种冲突类型自动检测，阻断错误决策
2. **Token 账单失控** → 按 Agent 归因成本，预算熔断自动止损
3. **审计合规无法交差** → SHA-256 防篡改哈希链，SOC2/ISO27001 一键导出
4. **Agent 挂了没人知道** → 心跳监控 + P50/P95/P99 延迟 + 流水线可视化
5. **Prompt 注入攻击** → 13 种注入模式检测 + 身份证/手机号/邮箱自动脱敏

---

## 谁在用？

- 你正在用 LangChain / CrewAI 搭 Agent，老板问"这东西安全吗"，你拿不出监控面板
- 月底要过合规审计，审计师要求提供所有 Agent 的决策追溯日志
- 管理 20+ 个 Agent，不知道各自花了多少钱、输出有没有矛盾
- 企业接入 AI 后面临监管检查，需要 SOC 2 / ISO 27001 / 等保合规证据

**如果你的团队正在经历以上任何一种情况——这个项目就是为你做的。**

---

## 和市面上其他工具有什么区别？

| 能力 | Ahy Governance | LangSmith | LangFuse | Datadog |
|------|---------------|-----------|----------|---------|
| LLM 调用追踪 | ✅ | ✅ | ✅ | ✅ |
| **多 Agent 冲突检测** | ✅ 5 种类型 | ❌ | ❌ | ❌ |
| **按 Agent 归因成本** | ✅ | 部分 | 部分 | ❌ |
| **防篡改审计（SHA-256）** | ✅ SOC2/ISO | ❌ | ❌ | 部分 |
| **三级权限 + API Key** | ✅ | ❌ | ❌ | ✅ |
| **Prompt 注入防御** | ✅ 13 规则 | ❌ | ❌ | ❌ |
| **跨 Agent 记忆共享** | ✅ 命名空间隔离 | ❌ | ❌ | ❌ |
| **计费模式** | 按 Agent 数 | 按人头 | 按人头 | 按主机 |
| **开源** | ✅ MIT | ❌ | ✅ MIT | ❌ |

> LangSmith 和 LangFuse 是很优秀的 LLM 可观测性工具。但它们追踪的是单次 API 调用，不理解多 Agent 编排逻辑。Ahy Governance 专为 5 个以上 Agent 协同工作的场景设计——冲突检测、成本归因、审计合规，这些是单 Agent 追踪工具做不到的。

---

## 快速开始

```bash
pip install ahy-governance[web]
ahy-dashboard
# 浏览器打开 http://localhost:8080，点 "Demo Data" 查看演示数据
```

模块化调用：

```python
from ahy_governance import ConflictDetector, CostTracker, AuditReporter

# 检测 Agent 之间的冲突
detector = ConflictDetector()
conflicts = detector.check(agent_outputs, dag_definition)

# 按 Agent 追踪成本
tracker = CostTracker()
tracker.set_budget(limit_usd=100)
tracker.track("Planner", "claude-opus-4-7", tokens_in=15000, tokens_out=8000)

# 防篡改审计日志
auditor = AuditReporter()
auditor.log(AuditEventType.AGENT_START, "Planner", {"task": "plan"})
```

---

## Web 控制台

一行命令启动，7 个面板，5 秒自动刷新：

```
ahy-dashboard
```

| 面板 | 功能 |
|------|------|
| **Dashboard** | 总览：Agent 健康、总成本、审计完整性、预算使用率 |
| **Health** | Agent 健康表：状态徽章、P50/P95/P99 延迟、成功率 |
| **Cost** | 预算仪表 + 按 Agent/模型分解成本 + 详细调用记录 |
| **Conflicts** | 冲突检测沙箱：粘贴 JSON 输出 + DAG，一键检测 |
| **Audit** | 哈希链审计日志 + 完整性验证 + SOC2/ISO27001 导出 |
| **Memory** | 命名空间浏览器 + 键值搜索 + 跨 Agent 共享状态 |
| **Security** | RBAC 权限管理 + Prompt Guard 注入检测沙箱 |

![Dashboard screenshot](docs/dashboard.png)

---

## 架构

```
┌──────────────────────────────────────────────────────┐
│              Ahy Governance 控制台                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐  │
│  │ 冲突检测  │ │ 成本追踪  │ │ 审计报告  │ │ 健康监控│  │
│  └──────────┘ └──────────┘ └──────────┘ └────────┘  │
├──────────────────────────────────────────────────────┤
│                 治理核心层                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────────┐  │
│  │ 记忆共享  │ │   RBAC   │ │    Prompt Guard      │  │
│  │          │ │ 权限管理  │ │  (注入检测+脱敏)      │  │
│  └──────────┘ └──────────┘ └──────────────────────┘  │
├──────────────────────────────────────────────────────┤
│        已有 Agent 框架（自带，本仓库不包含）              │
│      Orchestrator  │  TraceLogger  │  Router         │
└──────────────────────────────────────────────────────┘
```

---

## 七大模块（全部完成）

| # | 模块 | 测试 | 功能说明 |
|---|------|------|---------|
| 1 | 冲突检测器 | 23 | 事实冲突、格式不匹配、依赖断裂、范围重叠、置信度冲突 |
| 2 | 成本追踪器 | 46 | 22 个模型定价、预算熔断、按 Agent 归因 |
| 3 | 审计报告器 | 35 | SHA-256 哈希链、SOC2/ISO27001 合规报告一键导出 |
| 4 | 健康监控器 | 45 | 心跳、P50-P99 延迟、错误率、DAG 流水线状态追踪 |
| 5 | RBAC 权限管理 | 41 | 三级角色、API Key 生命周期、多租户隔离 |
| 6 | Prompt Guard | 39 | 13 种注入模式检测、身份证/手机号/银行卡/邮箱脱敏 |
| 7 | 记忆共享 | 34 | 命名空间隔离、TTL 过期、标签搜索 |

**312 个测试，0 失败。** 每个模块通过 `get_X()` 获取内存单例，即开即用。

---

## SOC 2 / ISO 27001 合规

**审计报告器是整个平台最具商业价值的模块。** 它不只是记日志——它直接产出合规证据：

- **SHA-256 哈希链** — 每一条审计记录与上一条加密关联。篡改任何一条，整条链立即失效
- **SOC 2 报告** — 一键导出，覆盖安全性、可用性、机密性、处理完整性、隐私五大控制域
- **ISO 27001 报告** — Annex A 控制项（A.9/A.10/A.12/A.16/A.18）逐条标注合规/待审查状态

对于首次面临 AI 合规审计的企业：原本需要两周人工整理证据，现在 5 分钟导出一份合规报告。**SOC 2 合规包作为附加模块，+$299/月，所有付费层级均可开通。**

---

## 定价

**按 Agent 数计费** — 为你治理的 Agent 付费，不为人头付费。一个 20 人团队管理 50 个 Agent，付 50 个 Agent 的钱，不是 20 个座位的钱。

| 版本 | 价格 | Agent 数 | 包含 |
|------|------|---------|------|
| Community | 免费 | 1 | 全部 7 模块，本地部署 |
| Pro | $149/月 | 10 | 冲突检测、成本追踪、邮件支持 |
| Team | $499/月 | 50 | RBAC、审计报告、优先支持 |
| Enterprise | 联系我们 | 不限 | SSO/SAML、私有部署、SLA、专属支持 |

**SOC 2 合规包：** +$299/月 — 自动生成 SOC 2 / ISO 27001 合规审计报告，任意付费层级可用。

**Agent 治理集成服务：** ¥8-15 万/次 — MCP 连接器开发、私有化部署、定制规则配置。

---

## 生态

| 项目 | 说明 | 状态 |
|------|------|------|
| [Kingdee MCP Server](https://github.com/Leo-Ayh-Oday/kingdee-mcp-server) | AI Agent ↔ 金蝶云星空 ERP | ✅ MIT |
| [WeCom MCP Server](https://github.com/Leo-Ayh-Oday/wecom-mcp-server) | AI Agent ↔ 企业微信 | ✅ MIT |
| [Ahy Agent](https://github.com/Leo-Ayh-Oday/ahy-agent) | 多 Agent 编排引擎 | v0.6.0 |

---

## 社区

- **Discussions**: [GitHub Discussions](https://github.com/Leo-Ayh-Oday/ahy-governance/discussions) — 提问、建议、反馈
- **Issues**: [GitHub Issues](https://github.com/Leo-Ayh-Oday/ahy-governance/issues) — Bug 报告、功能请求
- **加星收藏**：如果觉得有用，给个 Star 让更多人看到

---

MIT License. Built by [Leo-Ayh-Oday](https://github.com/Leo-Ayh-Oday).
