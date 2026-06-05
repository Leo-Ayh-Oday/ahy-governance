# Ahy Governance

**开源 AI Agent 治理平台。自动发现 · 冲突检测 · 成本追踪 · 自愈恢复 · 审计存证 — 14 模块，900+ 测试，MIT。**

[![Tests](https://github.com/Leo-Ayh-Oday/ahy-governance/actions/workflows/test.yml/badge.svg)](https://github.com/Leo-Ayh-Oday/ahy-governance/actions/workflows/test.yml)
[![Coverage](https://img.shields.io/badge/coverage-81%25-brightgreen)](https://github.com/Leo-Ayh-Oday/ahy-governance/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/python-3.10_%7C_3.11_%7C_3.12-blue)](https://python.org)
[![PyPI](https://img.shields.io/pypi/v/ahy-governance?color=orange)](https://pypi.org/project/ahy-governance/)
[![Downloads](https://img.shields.io/pypi/dm/ahy-governance)](https://pypi.org/project/ahy-governance/)
[![License](https://img.shields.io/badge/license-MIT-purple)](LICENSE)
[![Stars](https://img.shields.io/github/stars/Leo-Ayh-Oday/ahy-governance?style=social)](https://github.com/Leo-Ayh-Oday/ahy-governance/stargazers)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

[English](README.md)

## 最近更新

- **AGP 自注册** — `.ahy-agent.json` 声明文件，自动发现 10 种框架的 Agent
- **18 个 MCP 工具** — 在 Claude Code、Cursor 里直接治理 Agent
- **三级自愈** — 规则匹配 → LLM 诊断 → 全自动闭环恢复
- **`@track` 装饰器** — 一行代码接入：成本、健康、审计全自动
- **Agent Level 分级** — Level 0-5 自动评估 + 治理策略推荐

## 解决什么问题

| 痛点 | Ahy Governance |
|------|---------------|
| Agent 之间互相矛盾？ | 5 种冲突类型自动检测 + 解析 |
| AI 成本不可预测？ | 实时预算监控 + 自动熔断 + 模型降级建议 |
| 审计合规交不了差？ | 5 分钟导出 SOC2 / ISO27001 证据报告 |
| Prompt 注入攻击？ | 13 种注入模式检测 + PII 自动脱敏 |
| Agent 凌晨挂了没人管？ | 三级自愈：规则 → LLM 诊断 → 全自动恢复 |
| 不知道有多少个 Agent 在跑？ | AGP 自动发现，扫 `.ahy-agent.json` |

---

## 使用前后对比

| | 不用 ahy-governance | 用了 ahy-governance |
|------|---------|------|
| 运维负担 | 1 人，每天 2 小时盯着 | 每天 10 分钟看摘要 |
| 冲突事故 | 每月 3-5 次业务错误 | 自动检测 + 解析，0 事故 |
| 合规审计 | 2 周手工翻日志 | 一键导出，10 分钟 |
| AI 支出 | 不可预测，月底超预算 | 实时可见 + 自动熔断 |
| 权限管理 | 权限混乱 | 自助角色管理 |

---

## 一行代码接入

```python
from ahy_governance import track

@track(name="my-agent", framework="langgraph", version="1.0.0")
def my_agent(query: str) -> str:
    return response
```

成本追踪、健康监控、审计日志、自动注册——全在 `@track` 里。CrewAI 和 LangChain 有原生适配器。

---

## 和市面上其他工具有什么区别？

LangSmith 和 LangFuse 是优秀的 LLM 追踪工具，但它们不理解多 Agent 编排逻辑。Ahy Governance 专为 5 个以上 Agent 协同工作的场景设计。

| 能力 | Ahy Governance | LangSmith | LangFuse | Datadog |
|------|---------------|-----------|----------|---------|
| LLM 调用追踪 | ✅ | ✅ | ✅ | ✅ |
| **多 Agent 冲突检测** | ✅ 5 种类型 | ❌ | ❌ | ❌ |
| **按 Agent 归因成本** | ✅ 含降级建议 | 部分 | 部分 | ❌ |
| **防篡改审计（SHA-256）** | ✅ SOC2/ISO | ❌ | ❌ | 部分 |
| **三级权限 + API Key** | ✅ | ❌ | ❌ | ✅ |
| **Prompt 注入防御** | ✅ 18 条策略 | ❌ | ❌ | ❌ |
| **三级自愈恢复** | ✅ 规则+LLM+全自动 | ❌ | ❌ | ❌ |
| **Agent 自动发现** | ✅ AGP 声明式 | ❌ | ❌ | ❌ |
| **跨 Agent 记忆共享** | ✅ 命名空间隔离 | ❌ | ❌ | ❌ |
| **开源** | ✅ MIT | ❌ | ✅ MIT | ❌ |

---

## 快速开始

```bash
pip install ahy-governance[web]
ahy-dashboard
# 浏览器打开 http://localhost:8081，点 "Demo Data" 查看演示数据
```

MCP 集成——在 Claude Code 里直接治理 Agent：

```bash
ahygen mcp init > .mcp.json
# 18 个治理工具现在可直接在 MCP 客户端中使用
```

```python
from ahy_governance import track

@track(name="my-agent", framework="langgraph", version="1.0.0")
def my_agent(query: str) -> str:
    return response
```

---

## Web 控制台

一行命令启动，7 个面板，深色主题，自动刷新：

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
┌──────────────────────────────────────────────────────────────┐
│                  Ahy Governance 控制台                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │ 冲突检测  │ │ 成本追踪  │ │ 审计报告  │ │   健康监控     │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│                     治理核心层                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ 记忆共享  │ │   RBAC   │ │  Prompt  │ │   自愈恢复       │ │
│  │          │ │ 权限管理  │ │  Guard   │ │   (三级递进)     │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘ │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────┐  │
│  │  Agent 发现      │ │  异常检测        │ │  Agent 分级  │  │
│  │  (AGP 声明式)    │ │                 │ │  (Level 0-5) │  │
│  └──────────────────┘ └──────────────────┘ └──────────────┘  │
├──────────────────────────────────────────────────────────────┤
│                    MCP 接口 (18 工具)                         │
│   成本 │ 消毒 │ 健康 │ 自愈 │ 审计 │ 评估 │ 管理              │
├──────────────────────────────────────────────────────────────┤
│         已有 Agent 框架（自带，本仓库不包含）                    │
│    CrewAI │ LangChain │ AutoGen │ OpenAI │ Claude Code       │
└──────────────────────────────────────────────────────────────┘
```

---

## 模块总览

| # | 模块 | 功能说明 |
|---|------|---------|
| 1 | 冲突检测器 | 5 种冲突类型：事实、格式、依赖、范围、置信度 + 语义冲突 |
| 2 | 成本追踪器 | 22 个模型定价、预算熔断、成本顾问（含模型降级建议） |
| 3 | 审计报告器 | SHA-256 哈希链、SOC2/ISO27001 合规报告、防篡改验证 |
| 4 | 健康监控器 | 心跳、P50-P99 延迟、错误率、DAG 流水线状态追踪 |
| 5 | 鉴权与权限 | 邮箱/密码 + JWT、三级角色、API Key 生命周期 |
| 6 | Prompt Guard | 13 种注入模式、PII 脱敏、18 条防护策略、三个时间点拦截（pre/mid/post） |
| 7 | 记忆共享 | 命名空间隔离、TTL 过期、标签搜索 |
| 8 | 自愈恢复 | 三级恢复：规则 → LLM 诊断 → 全自动，从恢复账本中自动学习新规则 |
| 9 | Agent 发现 | AGP manifest 扫描 + 进程/端口 fallback，自动识别 10 种框架 |
| 10 | 异常检测 | Token 尖峰、重复调用、内存泄漏，自动触发自愈 |
| 11 | Agent 分级 | Level 0-5 成熟度评估 + 治理策略推荐 |
| 12 | MCP 服务器 | 18 个治理工具通过 FastMCP 暴露，stdio + SSE 双传输 |
| 13 | SDK 装饰器 | `@track` 一行接入，支持同步/异步，CrewAI + LangChain 适配器 |
| 14 | 质量门 | 数据集 + 打分器评估，通过/不通过阈值，CI/CD 集成 |

**900+ 测试，0 失败。**

---

## SOC 2 / ISO 27001 合规

**审计报告器** 提供加密审计日志：

- **SHA-256 哈希链** — 每一条审计记录与上一条加密关联，篡改任何一条整条链立即失效
- **SOC 2 报告** — 一键导出，覆盖安全性、可用性、机密性、处理完整性、隐私五大控制域
- **ISO 27001 报告** — Annex A 控制项逐条标注合规/待审查状态

---

## 联系

有问题或反馈？提 Issue 或邮件 [2115464137@qq.com](mailto:2115464137@qq.com)。

---

## 生态

| 项目 | 说明 | 状态 |
|------|------|------|
| [Ahy Agent](https://github.com/Leo-Ayh-Oday/ahy-agent) | 多 Agent 编排引擎（DAG + 四层压缩 + 三路记忆） | v0.6.0 |
| [Kingdee MCP Server](https://github.com/Leo-Ayh-Oday/kingdee-mcp-server) | AI Agent ↔ 金蝶云星空 ERP，7 工具，11 类业务单据 | ✅ MIT |
| [WeCom MCP Server](https://github.com/Leo-Ayh-Oday/wecom-mcp-server) | AI Agent ↔ 企业微信，5 种消息类型 | ✅ MIT |
| [cognitio](https://github.com/Leo-Ayh-Oday/cognitio) | 多 LLM 认知推演引擎，三轮协商协议 | ✅ |

---

## 社区

- **Discussions**: [GitHub Discussions](https://github.com/Leo-Ayh-Oday/ahy-governance/discussions) — 提问、建议、反馈
- **Issues**: [GitHub Issues](https://github.com/Leo-Ayh-Oday/ahy-governance/issues) — Bug 报告、功能请求
- **加星收藏**：如果觉得有用，给个 Star 让更多人看到

---

## 参与贡献

欢迎提 PR。详见 [CONTRIBUTING_CN.md](CONTRIBUTING_CN.md) 了解开发环境搭建、代码风格和 PR 流程。

本项目遵循 [Contributor Covenant](CODE_OF_CONDUCT.md) 行为准则。
安全漏洞请查看 [SECURITY_CN.md](SECURITY_CN.md) 了解报告流程。

---

MIT License. Built by [Leo-Ayh-Oday](https://github.com/Leo-Ayh-Oday).
