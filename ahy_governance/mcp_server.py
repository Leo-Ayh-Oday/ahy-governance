"""Ahy Governance MCP Server — Expose governance tools via FastMCP.

Usage:
  python -m ahy_governance.mcp_server          # stdio transport
  ahy-governance-mcp                             # console script

Environment:
  AHY_DB_PATH     — SQLite database path (default: ahy_governance.db)
  AHY_MCP_ADMIN   — Set to "1" to expose admin tools (default: disabled)
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastmcp import FastMCP

# ── Server ────────────────────────────────────────────────────

mcp = FastMCP("ahy-governance")

# ── Lazy DB init ──────────────────────────────────────────────

_db = None


def _ensure_db():
    global _db
    if _db is None:
        from .storage import create_database
        db_path = os.environ.get("AHY_DB_PATH", "ahy_governance.db")
        _db = create_database(db_path)
    return _db


def _to_json(obj: Any) -> str:
    """Serialize to JSON string for MCP return values."""
    if isinstance(obj, str):
        return obj
    if hasattr(obj, "to_dict"):
        return json.dumps(obj.to_dict(), ensure_ascii=False, indent=2)
    if hasattr(obj, "__dict__"):
        return json.dumps(
            {k: v for k, v in obj.__dict__.items() if not k.startswith("_")},
            ensure_ascii=False, indent=2, default=str,
        )
    if isinstance(obj, list):
        items = []
        for item in obj:
            if hasattr(item, "to_dict"):
                items.append(item.to_dict())
            elif hasattr(item, "__dict__"):
                items.append(
                    {k: v for k, v in item.__dict__.items() if not k.startswith("_")}
                )
            else:
                items.append(item)
        return json.dumps(items, ensure_ascii=False, indent=2, default=str)
    if isinstance(obj, dict):
        return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


# ── Core Tools ────────────────────────────────────────────────

@mcp.tool()
def ahy_track_cost(
    agent_name: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    session_id: str = "",
) -> str:
    """Track token cost for an agent call. Returns cost summary."""
    from .cost_tracker import get_tracker
    db = _ensure_db()
    tracker = get_tracker()
    if tracker._db is None:
        tracker.set_database(db)
    entry = tracker.track(agent_name, model, tokens_in, tokens_out, session_id)
    return _to_json(entry)


@mcp.tool()
def ahy_check_health(agent_name: str) -> str:
    """Check health metrics for a specific agent."""
    from .health_monitor import check_health
    metrics = check_health(agent_name)
    if metrics is None:
        return json.dumps({"error": f"Agent '{agent_name}' not found"})
    return _to_json(metrics)


@mcp.tool()
def ahy_check_conflicts(
    step_outputs_json: str,
    dag_json: str = "",
) -> str:
    """Detect conflicts between agent outputs. Pass step_outputs as JSON string."""
    from types import SimpleNamespace
    from .conflict_detector import check_conflicts
    raw = json.loads(step_outputs_json)
    dag = json.loads(dag_json) if dag_json else None
    # Wrap plain values in SimpleNamespace so check_conflicts can access .output
    step_outputs = {}
    for k, v in raw.items():
        if isinstance(v, dict) and "output" in v:
            step_outputs[k] = SimpleNamespace(**v)
        else:
            step_outputs[k] = SimpleNamespace(output=v)
    conflicts = check_conflicts(step_outputs, dag)
    return _to_json(conflicts)


@mcp.tool()
def ahy_auto_resolve(
    conflicts_json: str,
    step_outputs_json: str,
) -> str:
    """Auto-resolve detected conflicts. Pass conflicts and step_outputs as JSON."""
    from .auto_resolver import auto_resolve
    from .conflict_detector import Conflict, ConflictType, Severity

    raw_conflicts = json.loads(conflicts_json)
    step_outputs = json.loads(step_outputs_json)

    # Reconstruct Conflict objects from JSON
    conflicts = []
    for c in raw_conflicts:
        conflicts.append(Conflict(
            conflict_type=ConflictType(c["conflict_type"]),
            severity=Severity(c["severity"]),
            agents_involved=c.get("agents_involved", []),
            description=c.get("description", ""),
            evidence=c.get("evidence", {}),
            suggestion=c.get("suggestion", ""),
        ))

    resolutions = auto_resolve(conflicts, step_outputs)
    return _to_json(resolutions)


@mcp.tool()
def ahy_sanitize_prompt(text: str) -> str:
    """Sanitize a prompt for injection attacks and PII."""
    from .prompt_guard import sanitize_prompt
    result = sanitize_prompt(text)
    return _to_json(result)


@mcp.tool()
def ahy_log_audit(
    event_type: str,
    agent_name: str,
    details: str = "",
    session_id: str = "",
) -> str:
    """Log an audit event. event_type: one of agent_start, agent_complete, agent_error, agent_retry, pipeline_start, pipeline_complete, pipeline_blocked, conflict_detected, conflict_resolved, budget_warning, budget_exceeded, human_review, human_override, tool_call, config_change, model_change, permission_denied."""
    from .audit_logger import log_audit, AuditEventType
    et = AuditEventType(event_type)
    det = json.loads(details) if details else None
    entry = log_audit(et, agent_name, det, session_id)
    return _to_json(entry)


@mcp.tool()
def ahy_detect_anomalies() -> str:
    """Scan for anomalies across all agents (token spikes, repeated calls, etc.)."""
    from .anomaly_detector import detect_anomalies
    anomalies = detect_anomalies()
    return _to_json(anomalies)


# ── Self-Healing Tools ──────────────────────────────────────────

@mcp.tool()
def ahy_self_heal(
    agent_name: str,
    incident_type: str,
    error_message: str,
    context_json: str = "",
    self_heal_level: str = "",
    workspace_id: str = "",
) -> str:
    """Trigger self-healing for an agent. incident_type: hallucination, execution_error, timeout, rate_limit, auth_error, token_spike, memory_exhausted, dependency_failure, output_invalid, unknown. self_heal_level (optional override): rule_only, llm_assisted, full_auto."""
    from .self_healer import get_healer, SelfHealLevel, IncidentType
    level_override = None
    if self_heal_level:
        try:
            level_override = SelfHealLevel(self_heal_level)
        except ValueError:
            pass
    if level_override == SelfHealLevel.FULL_AUTO and not _full_auto_enabled():
        return json.dumps({
            "error": (
                "full_auto self-healing is disabled for MCP. "
                "Set AHY_MCP_FULL_AUTO=1 to enable."
            )
        }, ensure_ascii=False)
    healer = get_healer()
    try:
        it = IncidentType(incident_type)
    except ValueError:
        it = IncidentType.UNKNOWN
    try:
        ctx = json.loads(context_json) if context_json else {}
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON in context_json"}, ensure_ascii=False)
    result = healer.self_heal(agent_name, it, error_message, ctx,
                              workspace_id=workspace_id,
                              level_override=level_override)
    return _to_json(result)


@mcp.tool()
def ahy_list_recovery_rules() -> str:
    """List all current recovery rules in the self-healing rule library."""
    from .self_healer import get_healer
    healer = get_healer()
    rules = [r.to_dict() for r in healer.rules]
    return json.dumps(rules, ensure_ascii=False, indent=2)


@mcp.tool()
def ahy_recovery_history(
    agent_name: str = "",
    incident_type: str = "",
    workspace_id: str = "",
    limit: int = 100,
) -> str:
    """Query the recovery ledger for past self-healing incidents."""
    db = _ensure_db()
    from .self_healer import get_healer
    healer = get_healer()
    if healer.ledger._db is None:
        healer.set_database(db)
    entries = healer.ledger.query(
        agent_name=agent_name,
        incident_type=incident_type,
        workspace_id=workspace_id,
        limit=_clamp_limit(limit),
    )
    return json.dumps(entries, ensure_ascii=False, indent=2, default=str)


@mcp.tool()
def ahy_scan_and_learn(workspace_id: str = "") -> str:
    """Scan recovery ledger and learn new rules from successful LLM diagnoses."""
    db = _ensure_db()
    from .self_healer import get_healer
    from .recovery_learner import get_learner
    healer = get_healer()
    learner = get_learner()
    if healer.ledger._db is None:
        healer.set_database(db)
    learner.set_database(db)
    learner.set_rule_engine(healer._rule_engine)
    result = learner.scan_and_learn(workspace_id)
    return _to_json(result)


@mcp.tool()
def ahy_auto_heal_check(workspace_id: str = "") -> str:
    """Scan for unhealthy/offline agents and auto-trigger self-healing."""
    if not _full_auto_enabled():
        return json.dumps({
            "error": (
                "auto self-healing checks are disabled for MCP. "
                "Set AHY_MCP_FULL_AUTO=1 to enable."
            )
        }, ensure_ascii=False)
    from .health_monitor import get_monitor
    results = get_monitor().auto_heal_check(workspace_id)
    return json.dumps(results, ensure_ascii=False, indent=2, default=str)


# ── Evaluation Tools ──────────────────────────────────────────

@mcp.tool()
def ahy_list_scorers() -> str:
    """List all available evaluation scorers."""
    from .evaluator import get_eval_registry
    scorers = get_eval_registry().list_scorers()
    return json.dumps(scorers, ensure_ascii=False, indent=2)


@mcp.tool()
def ahy_run_eval(
    dataset_id: str,
    scorer_names_json: str,
    workspace_id: str = "",
) -> str:
    """Run evaluation scorers against a dataset. scorer_names_json: JSON array of scorer names like ["hallucination_check","output_schema"]."""
    from .evaluator import get_eval_registry
    names = json.loads(scorer_names_json)
    db = _ensure_db()
    registry = get_eval_registry()
    if registry._db is None:
        registry.set_database(db)
    result = registry.run_eval(dataset_id, names, workspace_id)
    return _to_json(result)


@mcp.tool()
def ahy_create_dataset(
    name: str,
    cases_json: str,
    description: str = "",
    workspace_id: str = "",
) -> str:
    """Create an eval dataset from JSON. cases_json: [{"input": {...}, "expected": {...}, "tags": [...]}, ...]"""
    from .evaluator import get_eval_registry, EvalCase
    raw = json.loads(cases_json)
    cases = [EvalCase(
        case_id=f"case-{i:04d}",
        input=c.get("input", {}),
        expected=c.get("expected"),
        tags=c.get("tags", []),
    ) for i, c in enumerate(raw)]
    db = _ensure_db()
    registry = get_eval_registry()
    if registry._db is None:
        registry.set_database(db)
    ds_id = registry.create_dataset(name, cases, description, workspace_id)
    return json.dumps({"dataset_id": ds_id, "case_count": len(cases)}, ensure_ascii=False)


@mcp.tool()
def ahy_eval_report(
    dataset_id: str = "",
    workspace_id: str = "",
    limit: int = 50,
) -> str:
    """Query evaluation run history and reports."""
    from .evaluator import get_eval_registry
    db = _ensure_db()
    registry = get_eval_registry()
    if registry._db is None:
        registry.set_database(db)
    runs = registry.list_runs(dataset_id, workspace_id, limit)
    return json.dumps(runs, ensure_ascii=False, indent=2)


# ── Guardrail Tools ────────────────────────────────────────────

@mcp.tool()
def ahy_list_policies() -> str:
    """List all available guardrail policies."""
    from .output_guard import get_output_guard
    return json.dumps(get_output_guard().list_policies(), ensure_ascii=False, indent=2)


@mcp.tool()
def ahy_check_policy(
    agent_name: str,
    event_type: str,
    input_json: str = "{}",
    timing: str = "pre",
) -> str:
    """Check guardrail policies against input. timing: pre, mid, post."""
    from .output_guard import get_output_guard
    guard = get_output_guard()
    data = json.loads(input_json)
    if timing == "pre":
        result = guard.check_pre(agent_name, event_type, data)
    elif timing == "mid":
        result = guard.check_mid(agent_name, data)
    else:
        result = guard.check_post(agent_name, data)
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)


@mcp.tool()
def ahy_update_policy(policy_id: str, enabled: bool) -> str:
    """Enable or disable a guardrail policy."""
    from .output_guard import get_output_guard
    get_output_guard().update_policy(policy_id, enabled)
    return json.dumps({"policy_id": policy_id, "enabled": enabled}, ensure_ascii=False)


# ── Quality Gate Tools ─────────────────────────────────────────

@mcp.tool()
def ahy_run_quality_gate(
    gate_id: str,
    dataset_id: str,
    scorers_json: str,
    thresholds_json: str = "{}",
    workspace_id: str = "",
) -> str:
    """Run a quality gate against a dataset. scorers_json: ["s1","s2"]. thresholds_json: {"s1":0.8,"overall":0.7}."""
    from .quality_gate import GateConfig, QualityGate
    scorers = json.loads(scorers_json)
    thresholds = json.loads(thresholds_json)
    db = _ensure_db()
    config = GateConfig(gate_id=gate_id, dataset_id=dataset_id,
                        scorers=scorers, thresholds=thresholds)
    gate = QualityGate(gate_id, config)
    gate.set_database(db)
    result = gate.run(workspace_id)
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)


@mcp.tool()
def ahy_gate_history(workspace_id: str = "", limit: int = 50) -> str:
    """Query quality gate run history (uses eval runs as backing store)."""
    from .evaluator import get_eval_registry
    db = _ensure_db()
    registry = get_eval_registry()
    if registry._db is None:
        registry.set_database(db)
    runs = registry.list_runs(workspace_id=workspace_id, limit=limit)
    return json.dumps(runs, ensure_ascii=False, indent=2)


# ── Memory Tools ──────────────────────────────────────────────

@mcp.tool()
def ahy_memory_write(
    namespace: str,
    key: str,
    value: str,
    source_agent: str = "",
) -> str:
    """Write a value to shared agent memory."""
    from .memory_sharing import shared_memory_write
    entry = shared_memory_write(namespace, key, value, source_agent)
    return _to_json(entry)


@mcp.tool()
def ahy_memory_read(namespace: str, key: str) -> str:
    """Read a value from shared agent memory."""
    from .memory_sharing import shared_memory_read
    entry = shared_memory_read(namespace, key)
    if entry is None:
        return json.dumps({"error": "not found"})
    return _to_json(entry)


# ── Analysis Tools ────────────────────────────────────────────

@mcp.tool()
def ahy_analyze_costs() -> str:
    """Analyze costs and get optimization recommendations (model downgrade, token savings)."""
    from .cost_advisor import analyze_costs
    recs = analyze_costs()
    return _to_json(recs)


@mcp.tool()
def ahy_generate_compliance_report(
    report_type: str,
    workspace_id: str = "",
) -> str:
    """Generate a compliance report. report_type: algorithm_filing, safety_assessment, data_export."""
    from .compliance_reporter import get_reporter
    reporter = get_reporter()
    report = reporter.generate(report_type, workspace_id)
    return _to_json(report)


@mcp.tool()
def ahy_evaluate_agent_level(
    can_read: bool = False,
    can_search: bool = False,
    can_draft: bool = False,
    can_write_local: bool = False,
    can_write_external: bool = False,
    can_execute_code: bool = False,
    can_use_financial_tools: bool = False,
    can_communicate_externally: bool = False,
    requires_approval: bool = True,
    has_budget_controls: bool = False,
    has_durable_state: bool = False,
    has_checkpoint_recovery: bool = False,
    max_tool_risk: str = "read_only",
) -> str:
    """Evaluate an agent's maturity level (Level 0-5) and get recommended governance strategy.

    Based on agents-best-practices grading system. Returns the agent level,
    recommended governance controls, and allowed risk classes.
    """
    from .policy_engine import (
        AgentCapabilities, RiskClass, evaluate_agent_level, recommend_strategy,
    )
    try:
        risk = RiskClass(max_tool_risk)
    except ValueError:
        risk = RiskClass.READ_ONLY
    caps = AgentCapabilities(
        can_read=can_read,
        can_search=can_search,
        can_draft=can_draft,
        can_write_local=can_write_local,
        can_write_external=can_write_external,
        can_execute_code=can_execute_code,
        can_use_financial_tools=can_use_financial_tools,
        can_communicate_externally=can_communicate_externally,
        requires_approval=requires_approval,
        has_budget_controls=has_budget_controls,
        has_durable_state=has_durable_state,
        has_checkpoint_recovery=has_checkpoint_recovery,
        max_tool_risk=risk,
    )
    level = evaluate_agent_level(caps)
    strategy = recommend_strategy(level)
    return _to_json({
        "level": level.value,
        "level_label": strategy.label,
        "description": strategy.description,
        "required_controls": strategy.required_controls,
        "risk_classes_allowed": [r.value for r in strategy.risk_classes_allowed],
        "governance": strategy.to_dict(),
    })


# ── Admin Tools (gated by AHY_MCP_ADMIN=1) ───────────────────

def _admin_enabled() -> bool:
    return os.environ.get("AHY_MCP_ADMIN", "0") == "1"


def _full_auto_enabled() -> bool:
    return os.environ.get("AHY_MCP_FULL_AUTO", "0") == "1"


def _clamp_limit(limit: int, default: int = 100, maximum: int = 500) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, maximum))


def _admin_guard():
    if not _admin_enabled():
        raise PermissionError(
            "Admin tools disabled. Set AHY_MCP_ADMIN=1 to enable."
        )


@mcp.tool()
def ahy_create_workspace(name: str, owner_id: str) -> str:
    """Create a new workspace (admin only)."""
    _admin_guard()
    from .rbac import get_access_manager
    ws = get_access_manager().create_workspace(name, owner_id)
    return _to_json(ws)


@mcp.tool()
def ahy_add_user(
    workspace_id: str,
    user_id: str,
    role: str = "viewer",
) -> str:
    """Add a user to a workspace (admin only). role: admin, operator, viewer."""
    _admin_guard()
    from .rbac import get_access_manager, Role
    user = get_access_manager().add_user(workspace_id, user_id, Role(role))
    return _to_json(user)


@mcp.tool()
def ahy_create_api_key(
    workspace_id: str,
    user_id: str,
    name: str,
    role: str = "editor",
) -> str:
    """Create an API key for a user (admin only)."""
    _admin_guard()
    from .rbac import get_access_manager, Role
    api_key, raw = get_access_manager().create_api_key(
        workspace_id, user_id, name, Role(role),
    )
    return json.dumps({
        "key_id": api_key.key_id,
        "name": api_key.name,
        "role": api_key.role.value,
        "raw_key": raw,
    }, ensure_ascii=False)


@mcp.tool()
def ahy_send_alert(
    level: str,
    message: str,
    agent_name: str = "",
) -> str:
    """Send an alert via configured channels (admin only). level: info, warning, critical."""
    _admin_guard()
    from .webhook_alerts import get_alerter
    alerter = get_alerter()
    if alerter is None:
        return json.dumps({"error": "No alert channels configured"})
    from .webhook_alerts import Alert
    alert = Alert(
        title=f"[{level.upper()}] {agent_name or 'system'}",
        body=message,
        severity=level,
        source="mcp",
    )
    sent = alerter.send(alert)
    return json.dumps({"sent": sent, "level": level})


@mcp.tool()
def ahy_verify_audit_integrity(workspace_id: str = "") -> str:
    """Verify audit chain integrity (admin only)."""
    _admin_guard()
    from .audit_logger import get_auditor
    ok = get_auditor().verify_integrity(workspace_id)
    return json.dumps({"integrity_ok": ok})


@mcp.tool()
def ahy_get_dashboard(workspace_id: str = "") -> str:
    """Get the full governance dashboard — health, self-healing, evaluations, costs, guardrails (admin only)."""
    _admin_guard()
    from .health_monitor import get_monitor
    from .self_healer import get_healer
    from .output_guard import get_output_guard
    from .evaluator import get_eval_registry
    from .cost_tracker import get_tracker

    db = _ensure_db()
    monitor = get_monitor()
    healer = get_healer()
    guard = get_output_guard()
    registry = get_eval_registry()
    if registry._db is None:
        registry.set_database(db)
    tracker = get_tracker()

    health_data = monitor.get_dashboard_data(workspace_id)
    eval_runs = registry.list_runs(workspace_id=workspace_id, limit=10)
    recovery_entries = db.recovery_ledger_list(workspace_id=workspace_id, limit=100) if db.enabled else []
    auto_resolved = sum(1 for e in recovery_entries if e.get("diagnosed_by") in ("rule", "ledger"))
    rules = healer.rules
    total_cost = sum(e.cost_usd for e in tracker._entries) if tracker._entries else 0

    dashboard = {
        "agents": health_data,
        "self_healing": {
            "total_incidents": len(recovery_entries),
            "auto_resolved": auto_resolved,
            "escalated": len(recovery_entries) - auto_resolved,
            "rules_active": len(rules),
            "rules_learned": len([r for r in rules if r.id.startswith("learned-")]),
        },
        "evaluations": {
            "total_runs": len(eval_runs),
            "latest_score": float(eval_runs[0].get("summary_json", "{}")) if eval_runs else None,
        },
        "costs": {
            "total_usd": round(total_cost, 4),
        },
        "guardrails": {
            "policies_active": sum(1 for p in guard.list_policies() if p.get("enabled")),
            "policies_total": len(guard.list_policies()),
        },
    }
    return json.dumps(dashboard, ensure_ascii=False, indent=2, default=str)


# ── Entry point ───────────────────────────────────────────────

def main():
    """Run the MCP server via stdio transport."""
    mcp.run()


if __name__ == "__main__":
    main()
