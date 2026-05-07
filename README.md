# Ahy Governance

**Multi-Agent Governance Platform — 7 modules, 263 tests, pip install ready.**

[![Tests](https://img.shields.io/badge/tests-263%20passed-green)](https://github.com/Leo-Ayh-Oday/ahy-governance)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-purple)](LICENSE)

When you deploy 10+ AI agents, five things always break:
1. **Agents contradict each other** — Agent A says "low risk", Agent B says "critical"
2. **You have no idea what they cost** — token bills arrive blind
3. **Nobody audited what they did** — compliance nightmare
4. **Agents fail silently** — no heartbeat, no alert, pipeline broken
5. **No access control** — who can deploy agents? who can see data?
6. **Prompt injection attacks** — users inject malicious instructions

Ahy Governance solves all six.

---

## Features

### Phase 0 — MVP (Complete)

- [x] **Conflict Detector** — 5 conflict types (23 tests)
- [x] **Cost Tracker** — 20+ model pricing, budget circuit breaker (46 tests)
- [x] **Audit Reporter** — SHA-256 hash chain, SOC2/ISO27001 export (35 tests)
- [x] **Health Monitor** — Heartbeats, P50-P99 latency, error rates, DAG viz (45 tests)

### Phase 1 — Enterprise Ready (Complete)

- [x] **RBAC + API Key 管理** — 三级权限、密钥生命周期、多租户隔离 (41 tests)
- [x] **Prompt Guard** — 注入检测、PII脱敏, sanitize管道 (39 tests)

### Phase 2 — Moat + Hooks (Complete)

- [x] **Memory Sharing** — Namespace隔离、TTL过期、标签搜索 (34 tests)
- [ ] **MCP Connectors** — 飞书/企微/金蝶 MCP Server (独立 repo，开源钩子)

---

## Quick Start

```bash
pip install ahy-governance
```

```python
from ahy_governance import ConflictDetector

detector = ConflictDetector()
conflicts = detector.check(agent_outputs, dag_definition)

for c in conflicts:
    if c.severity == "CRITICAL":
        print(f"Pipeline blocked: {c.description}")
```

---

## Architecture

```
┌──────────────────────────────────────────┐
│           Ahy Governance Dashboard        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ Conflict │ │  Cost    │ │  Audit   │  │
│  │ Detector │ │ Tracker  │ │ Reporter │  │
│  └──────────┘ └──────────┘ └──────────┘  │
├──────────────────────────────────────────┤
│         Governance Core                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │  Memory  │ │   RBAC   │ │  Prompt  │  │
│  │ Sharing  │ │          │ │  Guard   │  │
│  └──────────┘ └──────────┘ └──────────┘  │
├──────────────────────────────────────────┤
│      Ahy Agent Core (existing)           │
│  Orchestrator │ TraceLogger │ Router     │
└──────────────────────────────────────────┘
```

---

## Why Ahy Governance?

| | Ahy Governance | APM Tools (Datadog/NewRelic) | DIY |
|---|---|---|---|
| Agent conflict detection | ✅ 5 conflict types | ❌ | ❌ |
| Per-agent cost attribution | ✅ | ❌ | Manual |
| Cross-agent memory sharing | ✅ | ❌ | ❌ |
| Audit trail | ✅ Tamper-proof | Partial | JSONL files |
| Open source | ✅ MIT | ❌ | N/A |

---

## Roadmap

- **Week 1-2 (Current)**: Conflict Detector ✅
- **Week 3**: Cost Tracker
- **Week 4**: Audit Reporter → **First Demo Video**
- **Week 5-8**: Dashboard + RBAC + Prompt Guard → **Product Launch**
- **Week 9-12**: Memory Sharing + MCP Connectors

---

## Contributing

PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

MIT — [LICENSE](LICENSE)

---

*Built by [Leo-Ayh-Oday](https://github.com/Leo-Ayh-Oday). Part of the Ahy Agent ecosystem.*
