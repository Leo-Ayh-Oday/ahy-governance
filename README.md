# Ahy Governance

**Multi-Agent Governance Platform — Conflict Detection, Cost Tracking, Audit Logging.**

[![Tests](https://img.shields.io/badge/tests-69%20passed-green)](https://github.com/Leo-Ayh-Oday/ahy-governance)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-purple)](LICENSE)

When you deploy 10+ AI agents, three things always break:
1. **Agents contradict each other** — Agent A says "low risk", Agent B says "critical"
2. **You have no idea what they cost** — token bills arrive blind
3. **Nobody audited what they did** — compliance nightmare

Ahy Governance solves all three.

---

## Features

### Phase 0 — MVP (In Progress)

- [x] **Conflict Detector** — 5 conflict types across agent outputs
  - Fact conflicts: two agents state contradictory data
  - Dependency breaks: downstream agent missing upstream fields
  - Format mismatches: type errors in agent handoffs
  - Scope overlaps: agents duplicating work
  - Confidence clashes: high vs low confidence disagreements
- [x] **Cost Tracker** — per-agent dollar cost attribution + budget circuit breaker
  - 20+ model pricing table (OpenAI, Anthropic, DeepSeek, Google, Meta, Mistral, Qwen)
  - Token → cost conversion, per-agent/session/model aggregation
  - Budget limits with auto-block and 80% alert threshold
  - CSV/JSON export, comprehensive cost reports
- [ ] **Audit Reporter** — tamper-proof audit logs + compliance export

### Coming
- Agent Health Dashboard (P50/P95/P99 latency, error rates, heartbeats)
- RBAC + Multi-tenant workspaces
- Prompt Injection Guard
- Cross-Agent Memory Sharing

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
