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
    from .health_monitor import get_monitor
    results = get_monitor().auto_heal_check(workspace_id)
    return json.dumps(results, ensure_ascii=False, indent=2, default=str)


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
    """Get the full health dashboard overview (admin only)."""
    _admin_guard()
    from .health_monitor import get_monitor
    dashboard = get_monitor().get_dashboard_data(workspace_id)
    return _to_json(dashboard)


# ── Entry point ───────────────────────────────────────────────

def main():
    """Run the MCP server via stdio transport."""
    mcp.run()


if __name__ == "__main__":
    main()
