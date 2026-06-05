# Changelog

All notable changes to Ahy Governance are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Recovery Learning Agent — auto-learn new self-healing rules from the recovery ledger
- DeepSeek LLMDoctor integration for LLM-assisted incident diagnosis
- Auto-trigger self-healing with checkpoint/restore context

## [0.9.0] — 2026-05-31

### Added
- **MCP Server** — 18 governance tools via FastMCP, stdio + SSE dual transport, compatible with Claude Code, Cursor, and any MCP client
- **Self-Healing (3 levels)** — rule-based recovery → LLM-assisted diagnosis → full-auto closed-loop recovery
- **`@track` Decorator** — one-line agent integration: `@track(name="agent", framework="langgraph")` adds cost tracking, health monitoring, audit logging, and auto-registration
- **Agent Level Grading** — Level 0-5 maturity evaluation with governance recommendations per level
- **Anomaly Detector** — token spike detection, repeated call detection, memory exhaustion monitoring, auto-triggers self-healing
- **SDK Decorator** — sync/async support, CrewAI and LangChain adapters
- **Quality Gate** — dataset + scorer evaluation with pass/fail thresholds, CI/CD integration
- **AGP Discovery** — agent manifest scanning with process/port fallback, auto-detect 10 frameworks
- Security hardening: PII redaction, prompt injection defense (13 patterns), 18 guardrail policies

### Changed
- Dashboard: 7 panels with dark theme, auto-refresh, RBAC workspace management
- CI/CD: ruff lint, bandit security scan, coverage gate at 80%
- Test coverage: 74% → 81% (141 new tests)

### Fixed
- MCP conflict check dict adaptation for nested agent outputs
- CostEntry.to_dict() now includes warning field
- MCP tools: DB injection hardening + graceful handling for unknown models

## [0.8.0] — 2026-05-07

### Added
- **Web Dashboard** — 7 panels: Dashboard, Health, Cost, Conflicts, Audit, Memory, Security
- **API Server** — FastAPI backend with REST endpoints for all modules
- **CI/CD Pipeline** — GitHub Actions with test, lint, and publish workflows
- Docker Compose deployment with Nginx reverse proxy

## [0.7.0] — 2026-05-08

### Added
- **PyPI Release** — `pip install ahy-governance[web]`
- **Audit Reporter** — SHA-256 hash chain, SOC2/ISO27001 compliance export
- **Cost Tracker** — 22 model pricings, budget circuit breaker, cost advisor
- **Conflict Detector** — 5 conflict types: fact, format, dependency, scope, confidence
- **Health Monitor** — heartbeats, P50-P99 latency, error rates
- **Auth & RBAC** — email/password + JWT, 3-tier roles, API key lifecycle
- SQLite persistence with dual-mode (SQLite/PostgreSQL)

## [0.1.0] — 2026-05-01

### Added
- Initial core governance library
- Multi-agent orchestration primitives
- Basic observability hooks

[Unreleased]: https://github.com/Leo-Ayh-Oday/ahy-governance/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/Leo-Ayh-Oday/ahy-governance/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/Leo-Ayh-Oday/ahy-governance/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/Leo-Ayh-Oday/ahy-governance/compare/v0.1.0...v0.7.0
[0.1.0]: https://github.com/Leo-Ayh-Oday/ahy-governance/releases/tag/v0.1.0
