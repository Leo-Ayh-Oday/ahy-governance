# Module Status Matrix

> Baseline: `audit-baseline-2026-07-31` (Commit `6345978` on `refactor/governance-runtime`)
> Updated: 2026-07-31

## Status Legend

| Status | Meaning |
|--------|---------|
| `WIRED` | Wired into the main governance runtime chain — evaluates → decides → enforces → audits automatically |
| `PARTIAL` | Partially wired — some integration exists but not a complete closed loop |
| `LIBRARY_ONLY` | Standalone API only — callers must manually invoke, no automatic enforcement |
| `METADATA_ONLY` | Defines config, policy catalog, or schema only — no runtime logic |
| `STUB` | Placeholder or unavailable in production |
| `PLANNED` | Design only, not yet implemented |

---

## Core Library (ahy_governance/)

### Governance Pipeline

| Module | Lines | Status | Wiring Notes |
|--------|-------|--------|-------------|
| `events.py` | 106 | LIBRARY_ONLY | 7 event dataclasses defined. Used by collector/decorator but not by any unified runtime. |
| `collector.py` | 190 | LIBRARY_ONLY | GovernancePipeline ABC. Used by decorator but no runtime-level dispatch. |
| `decorator.py` | 117 | PARTIAL | `@track` wraps agent lifecycle: `on_agent_start` → execute → `on_agent_end`. **Does NOT call `on_error`** on exception — exception is swallowed or not routed to governance pipeline. |

### Storage & Infrastructure

| Module | Lines | Status | Wiring Notes |
|--------|-------|--------|-------------|
| `storage.py` | 806 | LIBRARY_ONLY | SQLite backend. Used by web/MCP via `create_database()` factory. |
| `storage_pg.py` | 663 | LIBRARY_ONLY | PostgreSQL backend. Same interface as storage.Database. Not used by default. |
| `state_store.py` | 161 | LIBRARY_ONLY | Redis + MemoryStore fallback. GET/SET/INCR for budget/heartbeat sync. |
| `logging_config.py` | 71 | LIBRARY_ONLY | structlog setup. Used by web/server.py and some modules. |
| `migration.py` | 57 | LIBRARY_ONLY | Schema migration utilities. |
| `scaffold.py` | 155 | LIBRARY_ONLY | Project scaffolding helper. |
| `interfaces.py` | 149 | METADATA_ONLY | Abstract interfaces for enterprise modules. |

### Security & Identity

| Module | Lines | Status | Wiring Notes |
|--------|-------|--------|-------------|
| `auth.py` | 233 | LIBRARY_ONLY | JWT + API key auth. Used by web/server.py. Separate from AccessManager in RBAC. |
| `rbac.py` | 251 | LIBRARY_ONLY | 3-tier RBAC + API key lifecycle. Has own in-memory API key store not unified with auth.py. |
| `middleware.py` | 24 | PARTIAL | Workspace context extraction from headers. Web always resolves to anonymous — no real auth verification. |
| `prompt_guard.py` | 226 | LIBRARY_ONLY | 12+ injection patterns + PII masking. Has `sanitize()` API but caller must invoke manually; no automatic pre-LLM enforcement. |
| `output_guard.py` | 190 | PARTIAL | Output content guard. **Raises exception when no policies loaded** (default params bug). Not wired into post-LLM enforcement. |

### Governance Core

| Module | Lines | Status | Wiring Notes |
|--------|-------|--------|-------------|
| `policy_engine.py` | 533 | LIBRARY_ONLY | Agent Level 0-5 + 15 risk classes + GovernanceStrategy. Standalone API — no automatic evaluation on agent start. |
| `policy_catalog.py` | 79 | METADATA_ONLY | Policy catalog definitions. |
| `evaluator.py` | 365 | LIBRARY_ONLY | Dataset + scorer orchestration. **`run_eval()` scores `case.input` as output** — evaluation does not run real agent output. |
| `quality_gate.py` | 121 | LIBRARY_ONLY | Quality gate with pass/fail thresholds. No AgentRunner — cannot run agents to get actual output. No CI-blocking exit codes. |
| `conflict_detector.py` | 414 | LIBRARY_ONLY | Rule-based conflict detection + trust-weighted arbitration. Used by web/server.py manually. |
| `semantic_conflict.py` | 278 | LIBRARY_ONLY | Semantic/schema-level conflict detection. Not integrated into enforcement. |

### Observability

| Module | Lines | Status | Wiring Notes |
|--------|-------|--------|-------------|
| `cost_tracker.py` | 286 | LIBRARY_ONLY | Token→USD cost tracking + budget circuit breaker. **No pre-call budget reservation** — budget check happens after the call. |
| `cost_advisor.py` | 363 | LIBRARY_ONLY | Cost optimization recommendations. Not wired — recommendations are not automatically applied. |
| `audit_logger.py` | 339 | PARTIAL | SHA-256 hash chain + SOC2/ISO export. **Chain breaks on restart** — doesn't persist/restore index and root_hash. |
| `health_monitor.py` | 411 | LIBRARY_ONLY | Agent heartbeat + latency tracking. **Latency unit bug** — may use wrong time unit. |
| `anomaly_detector.py` | 338 | LIBRARY_ONLY | Token spike / repeated calls detection. **No real timestamp-based window** — uses cumulative list length. |
| `compliance_reporter.py` | 437 | LIBRARY_ONLY | Algorithm filing + safety assessment reports. |
| `webhook_alerts.py` | 335 | LIBRARY_ONLY | WeCom/DingTalk/Feishu/Slack channels. |

### Self-Healing & Recovery

| Module | Lines | Status | Wiring Notes |
|--------|-------|--------|-------------|
| `self_healer.py` | 526 | PARTIAL | Full diagnosis chain: incident detection → rule match → LLM diagnosis → RecoveryAction → RecoveryLedger. **Missing execution**: `_finalize()` writes `ATTEMPTED` and returns `HealResult` — never actually retries, restarts, or rolls back. |
| `recovery_rules.py` | 108 | METADATA_ONLY | Rule definitions. |
| `recovery_learner.py` | 255 | PARTIAL | Can learn candidate rules from ledger. Rules default to Disabled — never auto-enabled without manual review. No verifier feedback loop. |
| `auto_resolver.py` | 283 | LIBRARY_ONLY | Auto-resolution strategies. Not wired into enforcement. |
| `llm_diagnose.py` | 122 | LIBRARY_ONLY | DeepSeek LLMDoctor. Generates structured RecoveryAction. Called by SelfHealer. |
| `checkpoint_store.py` | 105 | PARTIAL | Can save/restore context. **Only returns `restore_context`** — no actual Resume Adapter, no state version, no schema. |

### Multi-Agent & Memory

| Module | Lines | Status | Wiring Notes |
|--------|-------|--------|-------------|
| `memory_sharing.py` | 181 | LIBRARY_ONLY | Cross-agent memory with namespace isolation. |
| `agent_registry.py` | 423 | LIBRARY_ONLY | AGP agent registry. **AGP has encoding corruption** (mojibake). **Missing workspace-scoped unique keys** — same agent name across workspaces may conflict. |
| `agent_discovery.py` | 306 | LIBRARY_ONLY | Local machine agent scanning. README claims "10 frameworks" but actual adapters only cover LangChain + CrewAI. |
| `agent_import_scanner.py` | 402 | LIBRARY_ONLY | Static import analysis for AGP manifests. |
| `substitute_client.py` | 123 | LIBRARY_ONLY | Model fallback client. |

### MCP Server

| Module | Lines | Status | Wiring Notes |
|--------|-------|--------|-------------|
| `mcp_server.py` | 595 | LIBRARY_ONLY | 19 MCP tools. Each tool uses local imports — no shared GovernanceRuntime. **Dashboard parsing bug**: `float(summary_json)` should be `json.loads(summary_json)`. |

### Framework Adapters

| Module | Lines | Status | Wiring Notes |
|--------|-------|--------|-------------|
| `adapters/langchain.py` | 189 | LIBRARY_ONLY | LangChain callbacks. Reports events but no enforcement capability. |
| `adapters/crewai.py` | 141 | LIBRARY_ONLY | CrewAI adapter. **Timing bug**: mixes `id(agent)` and `id(step)` as run_id. No before-step hook — only after-completion callback. |

---

## Web Dashboard (web/)

| Module | Lines | Status | Wiring Notes |
|--------|-------|--------|-------------|
| `server.py` | 1883 | LIBRARY_ONLY | 40+ FastAPI endpoints. Each endpoint manually imports and calls governance modules — no unified Gateway. **`/demo` endpoints expose write operations** without authentication. **Probe events reference non-existent enum values** and swallow exceptions. |

---

## Key: Top 10 Wiring Gaps (P0)

| # | Gap | Modules Affected | Impact |
|---|-----|-----------------|--------|
| 1 | No unified GovernanceRuntime | All evaluators + enforcers | Every module is a standalone library; no closed loop |
| 2 | `@track` doesn't call `on_error` | `decorator.py` | Agent exceptions never enter governance pipeline |
| 3 | SelfHealer doesn't execute actions | `self_healer.py` | Recovery actions are diagnosed but not performed |
| 4 | `run_eval()` scores input as output | `evaluator.py` | Evaluation metrics are meaningless |
| 5 | Audit chain breaks on restart | `audit_logger.py` | Audit integrity claim is false across restarts |
| 6 | No pre-call budget reservation | `cost_tracker.py` | Budget limit enforced after the fact |
| 7 | Web WorkspaceContext always anonymous | `middleware.py` | Multi-tenant isolation doesn't actually work |
| 8 | Health latency unit mismatch | `health_monitor.py` | 500ms latency may read as 500s |
| 9 | AGP encoding corruption + missing workspace keys | `agent_registry.py` | Agent identity unreliable |
| 10 | OutputGuard crashes on default config | `output_guard.py` | Default state is a crash, not safe allow |

---

## Gap → PR Mapping (Phase 0)

| Gap # | PR | Action |
|-------|-----|--------|
| 1 | PR-09–17 | Phased: Gateway → Context → Engine → Enforcer → Migration |
| 2 | PR-03 | Fix `@track` to call `pipeline.on_error()` |
| 3 | PR-12 (v0.12) | RecoveryActionExecutor + Verifier |
| 4 | PR-05 | Fix scoring object, add AgentRunner stub |
| 5 | PR-08 | Persist and restore audit chain per workspace |
| 6 | PR-15 | Budget preflight in Runtime Mode |
| 7 | PR-07 | Unify auth + real WorkspaceContext resolution |
| 8 | PR-04 | Standardize all time units to ms/seconds |
| 9 | PR-12 (Phase 8) | Fix encoding + add workspace_id to unique keys |
| 10 | PR-06 | Load default policies on init, fix default params |
