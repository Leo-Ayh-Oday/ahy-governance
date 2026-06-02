# Ahy Governance

**Open-source AI Agent governance. Deploy agents with confidence — conflict detection, cost control, audit trails, compliance ready.**

[![Tests](https://github.com/Leo-Ayh-Oday/ahy-governance/actions/workflows/test.yml/badge.svg)](https://github.com/Leo-Ayh-Oday/ahy-governance/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-purple)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.9.1-orange)](https://pypi.org/project/ahy-governance/)
[![Downloads](https://img.shields.io/pypi/dm/ahy-governance)](https://pypi.org/project/ahy-governance/)

[中文文档](README_CN.md)

## Recent Updates

- **AGP Self-Registration** — `.ahy-agent.json` manifest, auto-discover agents across 10 frameworks
- **18 MCP Tools** — govern agents directly from Claude Code, Cursor, or any MCP client
- **Self-Healing (3 levels)** — rule → LLM diagnosis → full auto closed-loop recovery
- **`@track` Decorator** — one line to integrate: cost, health, audit, all automatic
- **Agent Level Grading** — Level 0-5 auto-evaluation with governance recommendations

## What You Get

| Problem | Ahy Governance |
|---------|---------------|
| Agents conflicting with each other? | Auto-detect and resolve — 5 conflict types |
| AI costs unpredictable? | Real-time budget visibility + automatic circuit breaker + model downgrade suggestions |
| Auditor knocking? | 5-minute compliance evidence export (SOC2 / ISO27001) |
| Someone jailbreaking your AI? | Prompt injection detection + PII redaction |
| Agent crashed at 3am? | 3-level self-healing: rule → LLM diagnosis → full-auto recovery |
| Don't know how many agents you have? | AGP auto-discovery — scans `.ahy-agent.json` manifests |

---

## Before vs After

| | Without ahy-governance | With ahy-governance |
|------|---------|------|
| Ops burden | 1 person, 2 hrs/day monitoring | 10 min/day reading summaries |
| Conflict incidents | 3-5 business errors per month | Auto-detect + resolve, 0 incidents |
| Compliance audit | 2 weeks manual log gathering | One-click PDF export, 10 minutes |
| AI spending | Unpredictable, over budget monthly | Real-time visibility + auto circuit breaker |
| Access control | Permission chaos | Self-service role management |

---

## 1 Line to Integrate

```python
from ahy_governance import track

@track(name="my-agent", framework="langgraph", version="1.0.0")
def my_agent(query: str) -> str:
    return response
```

Cost tracking, health monitoring, audit logging, and auto-registration — all in `@track`. CrewAI and LangChain adapters available.

---

## Beyond LLM Observability

LangSmith and LangFuse are excellent LLM tracing tools, but they don't understand multi-agent orchestration.
Ahy Governance is purpose-built for teams running 5+ agents that collaborate, conflict, and need coordination.

| Capability | Ahy Governance | LangSmith | LangFuse | Datadog |
|------------|---------------|-----------|----------|---------|
| **Multi-agent conflict detection** | ✅ 5 types | ❌ | ❌ | ❌ |
| **Cross-agent cost attribution** | ✅ Per-agent | Partial | Partial | ❌ |
| **Tamper-proof audit (SHA-256)** | ✅ SOC2/ISO | ❌ | ❌ | Partial |
| **RBAC + API key management** | ✅ 3-tier | ❌ | ❌ | ✅ |
| **Prompt injection defense** | ✅ 13 rules | ❌ | ❌ | ❌ |
| **Cross-agent memory sharing** | ✅ Namespaced | ❌ | ❌ | ❌ |
| **Open source** | ✅ MIT | ❌ | ✅ MIT | ❌ |

---

## Who's It For

- You're building agents with LangChain / CrewAI and your boss asks "is this safe?"
- Compliance audit is coming and auditors want every AI decision traceable
- You manage 20+ agents and don't know who spent what or who's conflicting with whom
- You need SOC2 / ISO27001 evidence and Excel isn't cutting it anymore

---

## Quick Start

```bash
pip install ahy-governance[web]
ahy-dashboard
# Open http://localhost:8080 — click "Demo Data" to populate
```

Or use the MCP integration — govern agents directly from Claude Code:

```bash
ahygen mcp init > .mcp.json
# 18 governance tools now available in your MCP client
```

```python
from ahy_governance import track

@track(name="my-agent", framework="langgraph", version="1.0.0")
def my_agent(query: str) -> str:
    return response
```

---

## Web Dashboard

Launch with one command. 7 panels, dark theme, auto-refresh.

```
ahy-dashboard
```

| Panel | What it shows |
|-------|--------------|
| **Dashboard** | Agent health overview, total cost, audit integrity, budget gauge |
| **Health** | Per-agent status badges, P50/P95/P99 latency, success rates |
| **Cost** | Budget gauge, cost by agent/model, per-call entry log |
| **Conflicts** | JSON sandbox — paste outputs + DAG, click "Check" |
| **Audit** | Hash-chained event log, integrity verification, SOC2/ISO27001 export |
| **Memory** | Namespace browser, key-value search, cross-agent shared state |
| **Security** | RBAC workspace/user/key management + Prompt Guard sandbox |

![Dashboard screenshot](docs/dashboard.png)

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                  Ahy Governance Dashboard                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │ Conflict │ │   Cost   │ │  Audit   │ │    Health      │  │
│  │ Detector │ │ Tracker  │ │ Reporter │ │   Monitor      │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│                     Governance Core                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │  Memory  │ │   RBAC   │ │  Prompt  │ │  Self-Healing    │ │
│  │ Sharing  │ │          │ │  Guard   │ │  (3-level)       │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘ │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────┐  │
│  │ Agent Discovery  │ │  Anomaly         │ │  Agent Level  │  │
│  │ (AGP manifest)   │ │  Detector        │ │  Grading      │  │
│  └──────────────────┘ └──────────────────┘ └──────────────┘  │
├──────────────────────────────────────────────────────────────┤
│                      MCP Interface (18 tools)                 │
│   Cost │ Sanitize │ Health │ Self-Heal │ Audit │ Eval │ Admin │
├──────────────────────────────────────────────────────────────┤
│         Existing Agents (bring your own)                      │
│         CrewAI │ LangChain │ AutoGen │ OpenAI │ Claude Code   │
└──────────────────────────────────────────────────────────────┘
```

---

## Modules

| # | Module | Description |
|---|--------|-------------|
| 1 | Conflict Detector | 5 conflict types: fact, format, dependency, scope, confidence + semantic |
| 2 | Cost Tracker | 22 model pricings, budget circuit breaker, cost advisor with model downgrade suggestions |
| 3 | Audit Reporter | SHA-256 hash chain, SOC2/ISO27001 compliance export, tamper-proof verification |
| 4 | Health Monitor | Heartbeats, P50-P99 latency, error rates, DAG pipeline tracking |
| 5 | Auth & RBAC | Email/password + JWT, 3-tier roles, API key lifecycle |
| 6 | Prompt Guard | 13 injection patterns, PII redaction, 18 guardrail policies, 3 time points (pre/mid/post) |
| 7 | Memory Sharing | Namespaced key-value, TTL expiry, tag search |
| 8 | Self-Healing | 3-level recovery: rule → LLM diagnosis → full-auto, auto-learns new rules from recovery ledger |
| 9 | Agent Discovery | AGP manifest scan + process/port fallback, auto-detect 10 frameworks |
| 10 | Anomaly Detector | Token spikes, repeated calls, memory leaks, auto-trigger self-healing |
| 11 | Agent Level Grading | Level 0-5 maturity evaluation with governance recommendations |
| 12 | MCP Server | 18 governance tools via FastMCP, stdio + SSE dual transport |
| 13 | SDK Decorator | `@track` one-line integration, sync/async, CrewAI + LangChain adapters |
| 14 | Quality Gate | Dataset + scorer evaluation, pass/fail thresholds, CI/CD integration |

**900+ tests, 0 failures.**

---

## SOC 2 / ISO 27001 Compliance

The **Audit Reporter** module provides cryptographic audit logging:

- **SHA-256 hash chain** — every audit entry is cryptographically linked to its predecessor
- **SOC 2 export** — one-click report covering Security, Availability, Confidentiality, Processing Integrity, and Privacy
- **ISO 27001 export** — Annex A controls with compliant/needs-review status per control

---

## Contact

Questions or feedback? Open an issue or email [2115464137@qq.com](mailto:2115464137@qq.com).

---

## Ecosystem

| Project | Description | Status |
|---------|-------------|--------|
| [Ahy Agent](https://github.com/Leo-Ayh-Oday/ahy-agent) | Multi-agent orchestration harness (DAG + 4-layer compression + triple memory) | v0.6.0 |
| [Kingdee MCP Server](https://github.com/Leo-Ayh-Oday/kingdee-mcp-server) | AI Agent ↔ 金蝶云星空 ERP, 7 tools, 11 document types | ✅ MIT |
| [WeCom MCP Server](https://github.com/Leo-Ayh-Oday/wecom-mcp-server) | AI Agent ↔ 企业微信, 5 message types | ✅ MIT |
| [cognitio](https://github.com/Leo-Ayh-Oday/cognitio) | Multi-LLM deliberation engine with 3-round negotiation protocol | ✅ |

---

## Community

- **Discussions**: [GitHub Discussions](https://github.com/Leo-Ayh-Oday/ahy-governance/discussions) — questions, ideas, feedback
- **Issues**: [GitHub Issues](https://github.com/Leo-Ayh-Oday/ahy-governance/issues) — bug reports, feature requests
- **Star the repo**: If this is useful, a star helps others discover it

---

## Contributing

PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

MIT License. Built by [Leo-Ayh-Oday](https://github.com/Leo-Ayh-Oday).
