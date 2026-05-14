# Ahy Governance

**Open-source AI Agent governance. Deploy agents with confidence — conflict detection, cost control, audit trails, compliance ready.**

[![Tests](https://github.com/Leo-Ayh-Oday/ahy-governance/actions/workflows/test.yml/badge.svg)](https://github.com/Leo-Ayh-Oday/ahy-governance/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-purple)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.8.0-orange)](https://pypi.org/project/ahy-governance/)
[![Downloads](https://img.shields.io/pypi/dm/ahy-governance)](https://pypi.org/project/ahy-governance/)

[中文文档](README_CN.md)

## Recent Updates

- **Web Dashboard** — one-command launch, dark monitoring theme, 7 live-updating panels
- **Transparent Proxy** — OpenAI-compatible endpoint, zero code changes for existing agents
- **Built-in Auth** — email/password login + JWT + API Key management
- **Docker Deploy** — single command, supports Zeabur / EdgeOne Pages

## What You Get

| Problem | Ahy Governance |
|---------|---------------|
| Agents conflicting with each other? | Auto-detect and resolve — 5 conflict types |
| AI costs unpredictable? | Real-time budget visibility + automatic circuit breaker |
| Auditor knocking? | 5-minute compliance evidence export (SOC2 / ISO27001) |
| Someone jailbreaking your AI? | Prompt injection detection + PII redaction |
| Intern fat-fingering production? | 3-tier RBAC — who can view, who can change |

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

## 3 Lines to Integrate

```python
from ahy_governance import ConflictDetector, CostTracker, AuditReporter

detector = ConflictDetector(); tracker = CostTracker(); auditor = AuditReporter()
```

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

Or use individual modules:

```python
from ahy_governance import ConflictDetector, CostTracker, AuditReporter

# Detect conflicts between agents
detector = ConflictDetector()
conflicts = detector.check(agent_outputs, dag_definition)

# Track costs per agent
tracker = CostTracker()
tracker.set_budget(limit_usd=100)
tracker.track("Planner", "claude-opus-4-7", tokens_in=15000, tokens_out=8000)

# Tamper-proof audit logging
auditor = AuditReporter()
auditor.log(AuditEventType.AGENT_START, "Planner", {"task": "plan"})
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
┌──────────────────────────────────────────────────────┐
│              Ahy Governance Dashboard                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐  │
│  │ Conflict │ │   Cost   │ │  Audit   │ │ Health │  │
│  │ Detector │ │ Tracker  │ │ Reporter │ │Monitor │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────┘  │
├──────────────────────────────────────────────────────┤
│                 Governance Core                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────────┐  │
│  │  Memory  │ │   RBAC   │ │    Prompt Guard      │  │
│  │ Sharing  │ │          │ │ (Injection + PII)    │  │
│  └──────────┘ └──────────┘ └──────────────────────┘  │
├──────────────────────────────────────────────────────┤
│      Existing Agent Core (not included — bring your own)  │
│      Orchestrator  │  TraceLogger  │  Router         │
└──────────────────────────────────────────────────────┘
```

---

## Modules (7/7 complete)

| # | Module | Tests | Description |
|---|--------|-------|-------------|
| 1 | Conflict Detector | 23 | 5 conflict types: fact, format, dependency, scope, confidence |
| 2 | Cost Tracker | 46 | 22 model pricings, budget circuit breaker, per-agent attribution |
| 3 | Audit Reporter | 35 | SHA-256 hash chain, SOC2/ISO27001 compliance export |
| 4 | Health Monitor | 45 | Heartbeats, P50-P99 latency, error rates, DAG pipeline tracking |
| 5 | Auth & RBAC | 59 | Email/password + JWT, 3-tier roles, API key lifecycle |
| 6 | Prompt Guard | 39 | 13 injection patterns, PII redaction, sanitize pipeline |
| 7 | Memory Sharing | 34 | Namespaced key-value, TTL expiry, tag search |

**384 tests, 0 failures.**

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
| [Kingdee MCP Server](https://github.com/Leo-Ayh-Oday/kingdee-mcp-server) | AI Agent ↔ 金蝶云星空 ERP | ✅ MIT |
| [WeCom MCP Server](https://github.com/Leo-Ayh-Oday/wecom-mcp-server) | AI Agent ↔ 企业微信 | ✅ MIT |
| [Ahy Agent](https://github.com/Leo-Ayh-Oday/ahy-agent) | Multi-agent orchestration harness | v0.6.0 |

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
