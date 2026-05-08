"""Ahy Governance Web Dashboard — FastAPI backend."""

from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, field_validator

from ahy_governance import (
    get_monitor,
    get_tracker,
    get_detector,
    get_auditor,
    get_access_manager,
    get_guard,
    get_memory_sharing,
    AuditEventType,
    Role,
    Permission,
    AgentStatus,
    check_conflicts,
)

app = FastAPI(title="Ahy Governance Dashboard", version="0.7.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = Path(__file__).parent

# ── Shared Demo Data ──────────────────────────────────────────────

AGENTS = ["Planner", "Executor", "Reviewer", "Analyst", "Governor"]
SESSIONS = ["sess-demo-1", "sess-demo-2", "sess-demo-3"]
MODELS = [
    ("claude-opus-4-7", "Anthropic"),
    ("claude-sonnet-4-6", "Anthropic"),
    ("gpt-4.1", "OpenAI"),
    ("deepseek-chat", "DeepSeek"),
]


def _reset_all():
    for getter in [get_monitor, get_tracker, get_auditor, get_detector,
                   get_access_manager, get_guard, get_memory_sharing]:
        inst = getter()
        if hasattr(inst, 'reset'):
            inst.reset()


# ── Pydantic Models ──────────────────────────────────────────────

_re_valid_name = r"^[\w\-\. ]{1,64}$"

class HeartbeatBody(BaseModel):
    agent_name: str
    status: str
    latency_ms: float

    @field_validator("agent_name")
    @classmethod
    def validate_agent_name(cls, v):
        import re
        if not re.match(_re_valid_name, v):
            raise ValueError("agent_name contains invalid characters")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v not in ("ok", "timeout", "error"):
            raise ValueError("status must be ok, timeout, or error")
        return v

    @field_validator("latency_ms")
    @classmethod
    def validate_latency(cls, v):
        if v < 0 or v > 3600000:
            raise ValueError("latency_ms out of range (0-3600000)")
        return v

class WorkspaceBody(BaseModel):
    name: str
    owner_user_id: str = "admin"

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not v or len(v) > 128:
            raise ValueError("name must be 1-128 characters")
        return v

class UserBody(BaseModel):
    user_id: str
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in ("admin", "operator", "viewer"):
            raise ValueError("role must be admin, operator, or viewer")
        return v

class ApiKeyBody(BaseModel):
    workspace_id: str
    user_id: str = ""
    name: str = "API Key"
    role: str = "viewer"
    expires_in_days: int | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in ("admin", "operator", "viewer"):
            raise ValueError("role must be admin, operator, or viewer")
        return v

class MemoryWriteBody(BaseModel):
    key: str
    value: str
    source_agent: str = ""
    tags: list[str] | None = None
    ttl_seconds: float | None = None

class GuardBody(BaseModel):
    text: str

class ConflictCheckBody(BaseModel):
    step_outputs: dict = {}
    dag: dict | None = None
    strict: bool = False

class BudgetBody(BaseModel):
    limit_usd: float
    period: str = "monthly"
    alert_threshold: float = 0.8
    auto_block: bool = False

# ── Static Files ──────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(WEB_DIR / "dashboard.html")


# ── Health Monitor ────────────────────────────────────────────────

@app.get("/api/health/dashboard")
async def health_dashboard():
    return get_monitor().get_dashboard_data()


@app.get("/api/health/agents")
async def health_agents():
    return get_monitor().get_all_health()


@app.get("/api/health/agents/{name}")
async def health_agent(name: str):
    data = get_monitor().get_agent_health(name)
    if data is None:
        return JSONResponse({"error": "Agent not found"}, 404)
    return data


@app.get("/api/health/unhealthy")
async def health_unhealthy():
    return get_monitor().get_unhealthy_agents()


@app.post("/api/health/heartbeat")
async def health_heartbeat(data: HeartbeatBody):
    return get_monitor().heartbeat(
        data.agent_name, data.status, data.latency_ms
    )


@app.post("/api/health/demo")
async def health_demo():
    m = get_monitor()
    import random
    # Each agent: (name, intended_status, base_latency_ms, error_count)
    agents = [
        ("Planner",    "healthy",   30,  0),
        ("Executor",   "healthy",   45,  0),
        ("Analyst",    "healthy",   38,  0),
        ("Reviewer",   "degraded",  220, 4),
        ("Governor",   "offline",   20,  0),
    ]
    for name, status, base_lat, errors in agents:
        if status != "offline":
            m.heartbeat(name, "ok", base_lat * 2)
        for i in range(20):
            is_error = (i >= (20 - errors))
            latency = base_lat * (0.6 + 0.8 * random.random())
            if is_error:
                latency = 200 + 150 * random.random()  # degraded zone (200-350ms)
            m.record_call(name, success=not is_error, latency_ms=latency)
    # Governor: no recent heartbeat → auto OFFLINE
    return {"ok": True}


# ── Cost Tracker ──────────────────────────────────────────────────

@app.get("/api/cost/report")
async def cost_report():
    return get_tracker().get_report()


@app.get("/api/cost/budget")
async def cost_budget_get():
    status = get_tracker().get_budget_status()
    if status is None:
        return JSONResponse({"error": "No budget configured"}, 404)
    return status


@app.post("/api/cost/budget")
async def cost_budget_set(data: BudgetBody):
    return get_tracker().set_budget(
        limit_usd=data.limit_usd,
        period=data.period,
        alert_threshold=data.alert_threshold,
        auto_block=data.auto_block,
    )


@app.get("/api/cost/pricing")
async def cost_pricing():
    tracker = get_tracker()
    return [tracker.get_pricing(m.model_id).__dict__ for m in tracker._pricing.values()]


@app.post("/api/cost/demo")
async def cost_demo():
    t = get_tracker()
    t.set_budget(50, "monthly", 0.8, False)
    costs = [
        ("Planner", "claude-opus-4-7", 15000, 8000),
        ("Planner", "claude-opus-4-7", 12000, 6000),
        ("Executor", "claude-sonnet-4-6", 25000, 15000),
        ("Executor", "claude-sonnet-4-6", 18000, 11000),
        ("Reviewer", "gpt-4.1", 8000, 5000),
        ("Reviewer", "gpt-4.1", 7000, 4000),
        ("Analyst", "deepseek-chat", 30000, 20000),
        ("Analyst", "deepseek-chat", 22000, 14000),
        ("Governor", "claude-sonnet-4-6", 5000, 3000),
        ("Planner", "claude-opus-4-7", 9000, 5000),
        ("Executor", "claude-sonnet-4-6", 14000, 9000),
        ("Reviewer", "gpt-4.1", 6000, 3500),
        ("Analyst", "deepseek-chat", 20000, 12000),
        ("Planner", "claude-sonnet-4-6", 10000, 7000),
        ("Executor", "gpt-4.1", 16000, 10000),
    ]
    for i, (agent, model, tin, tout) in enumerate(costs):
        t.track(agent, model, tin, tout, SESSIONS[i % 3])
    return {"ok": True}


# ── Conflict Detector ─────────────────────────────────────────────

@app.get("/api/conflicts/types")
async def conflict_types():
    from ahy_governance import ConflictType
    return [t.value for t in ConflictType]


@app.post("/api/conflicts/check")
async def conflict_check(data: ConflictCheckBody):
    from types import SimpleNamespace
    step_outputs = {}
    for key, val in data.step_outputs.items():
        if isinstance(val, dict):
            step_outputs[key] = SimpleNamespace(
                output=val.get("output", ""),
                confidence=val.get("confidence", 0.5),
                agent=val.get("agent", key),
            )
        else:
            step_outputs[key] = val
    return check_conflicts(step_outputs, data.dag, strict=data.strict)


@app.post("/api/conflicts/demo")
async def conflict_demo():
    """Return sample conflict detection data for the sandbox."""
    return {
        "sample_inputs": {
            "Planner": {
                "output": "Contract deadline is 2026-06-30, amount is $500,000, party A is Acme Corp.",
                "confidence": 0.95,
            },
            "Reviewer": {
                "output": "Contract deadline appears to be 2026-07-15 based on the amendment. Amount confirmed at $500,000.",
                "confidence": 0.85,
            },
            "Analyst": {
                "output": "Risk level: low. Compliance: partially met (missing GDPR clause).",
                "confidence": 0.72,
            },
        },
        "sample_dag": {
            "steps": ["Planner", "Reviewer", "Analyst"],
            "edges": [
                {"from": "Planner", "to": "Reviewer"},
                {"from": "Reviewer", "to": "Analyst"},
            ],
        },
    }


# ── Audit Logger ──────────────────────────────────────────────────

@app.get("/api/audit/recent")
async def audit_recent(n: int = Query(default=50)):
    return get_auditor().recent(n)


@app.get("/api/audit/integrity")
async def audit_integrity():
    return {"verified": get_auditor().verify_integrity()}


@app.get("/api/audit/query")
async def audit_query(
    agent_name: str | None = None,
    event_type: str | None = None,
    session_id: str | None = None,
):
    auditor = get_auditor()
    evt = AuditEventType(event_type) if event_type else None
    return auditor.query(agent_name=agent_name, event_type=evt, session_id=session_id)


@app.get("/api/audit/export/soc2")
async def audit_export_soc2():
    return get_auditor().export_soc2()


@app.get("/api/audit/export/iso27001")
async def audit_export_iso27001():
    return get_auditor().export_iso27001()


@app.post("/api/audit/demo")
async def audit_demo():
    a = get_auditor()
    events = [
        (AuditEventType.PIPELINE_START, "Governor", {"pipeline": "main-flow"}),
        (AuditEventType.AGENT_START, "Planner", {"task": "plan architecture"}),
        (AuditEventType.AGENT_COMPLETE, "Planner", {"duration_ms": 4500}),
        (AuditEventType.AGENT_START, "Executor", {"task": "implement module"}),
        (AuditEventType.AGENT_COMPLETE, "Executor", {"duration_ms": 12000}),
        (AuditEventType.AGENT_START, "Reviewer", {"task": "review code"}),
        (AuditEventType.CONFLICT_DETECTED, "Reviewer", {"type": "format_mismatch"}),
        (AuditEventType.HUMAN_REVIEW, "Reviewer", {"decision": "override"}),
        (AuditEventType.AGENT_RETRY, "Executor", {"attempt": 2}),
        (AuditEventType.AGENT_COMPLETE, "Reviewer", {"duration_ms": 8000}),
        (AuditEventType.AGENT_START, "Analyst", {"task": "analyze results"}),
        (AuditEventType.BUDGET_WARNING, "Analyst", {"usage_pct": 85.0}),
        (AuditEventType.AGENT_COMPLETE, "Analyst", {"duration_ms": 3000}),
        (AuditEventType.PIPELINE_COMPLETE, "Governor", {"pipeline": "main-flow"}),
        (AuditEventType.CONFIG_CHANGE, "Governor", {"setting": "model_switch", "to": "gpt-4.1"}),
    ]
    for evt, agent, details in events:
        a.log(evt, agent, details, SESSIONS[0])
    return {"ok": True}


# ── RBAC ──────────────────────────────────────────────────────────

@app.get("/api/rbac/workspaces")
async def rbac_workspaces():
    return get_access_manager().list_workspaces()


@app.post("/api/rbac/workspaces")
async def rbac_workspace_create(data: WorkspaceBody):
    return get_access_manager().create_workspace(data.name, data.owner_user_id)


@app.get("/api/rbac/workspaces/{ws_id}/users")
async def rbac_workspace_users(ws_id: str):
    return get_access_manager().get_users(ws_id)


@app.post("/api/rbac/workspaces/{ws_id}/users")
async def rbac_workspace_add_user(ws_id: str, data: UserBody):
    return get_access_manager().add_user(ws_id, data.user_id, Role(data.role))


@app.get("/api/rbac/workspaces/{ws_id}/api-keys")
async def rbac_workspace_keys(ws_id: str):
    return get_access_manager().get_api_keys(ws_id)


@app.post("/api/rbac/api-keys")
async def rbac_create_key(data: ApiKeyBody):
    key, raw = get_access_manager().create_api_key(
        workspace_id=data.workspace_id,
        user_id=data.user_id,
        name=data.name,
        role=Role(data.role),
        expires_in_days=data.expires_in_days,
    )
    result = key.to_dict()
    result["raw_key"] = raw
    return result


@app.post("/api/rbac/demo")
async def rbac_demo():
    am = get_access_manager()
    ws = am.create_workspace("Acme Corp Agents", "admin-1")
    am.add_user(ws.workspace_id, "admin-1", Role.ADMIN)
    am.add_user(ws.workspace_id, "op-alice", Role.OPERATOR)
    am.add_user(ws.workspace_id, "viewer-bob", Role.VIEWER)
    am.create_api_key(ws.workspace_id, "admin-1", "prod-key", Role.ADMIN)
    am.create_api_key(ws.workspace_id, "op-alice", "dev-key", Role.OPERATOR, 30)
    ws2 = am.create_workspace("Dev Sandbox", "admin-2")
    am.add_user(ws2.workspace_id, "admin-2", Role.ADMIN)
    return {"ok": True}


# ── Prompt Guard ──────────────────────────────────────────────────

@app.post("/api/guard/sanitize")
async def guard_sanitize(data: GuardBody):
    return get_guard().sanitize(data.text)


@app.post("/api/guard/detect")
async def guard_detect(data: GuardBody):
    return get_guard().detect_injection(data.text)


# ── Memory Sharing ────────────────────────────────────────────────

@app.get("/api/memory/namespaces")
async def memory_namespaces():
    return get_memory_sharing().list_namespaces()


@app.get("/api/memory/stats")
async def memory_stats():
    return get_memory_sharing().get_stats()


@app.post("/api/memory/demo")
async def memory_demo():
    m = get_memory_sharing()
    m.write("shared_config", "api_endpoint", "https://api.acme.com/v2", "Planner", ["config", "infra"])
    m.write("shared_config", "rate_limit", "1000 req/min", "Governor", ["config", "limit"])
    m.write("shared_config", "deployment_env", "production-us-east1", "Executor", ["infra"])
    m.write("agent_state", "Planner:last_plan", '{"version": 3, "steps": 12}', "Planner", ["state"], 3600)
    m.write("agent_state", "Executor:checkpoint", '{"completed": 8, "failed": 1}', "Executor", ["state"], 3600)
    m.write("knowledge", "soc2_requirements", "SOC2 Type II requires 6 months of audit data", "Analyst", ["compliance", "reference"])
    m.write("knowledge", "model_pricing_2026", '{"claude-opus": "$15/M", "gpt-4.1": "$10/M"}', "Analyst", ["pricing", "reference"])
    return {"ok": True}


@app.get("/api/memory/{namespace}")
async def memory_namespace_get(namespace: str):
    data = get_memory_sharing().get_namespace(namespace)
    if data is None:
        return JSONResponse({"error": "Namespace not found"}, 404)
    return data


@app.post("/api/memory/{namespace}")
async def memory_namespace_write(namespace: str, data: MemoryWriteBody):
    return get_memory_sharing().write(
        namespace=namespace,
        key=data.key,
        value=data.value,
        source_agent=data.source_agent,
        tags=data.tags,
        ttl_seconds=data.ttl_seconds,
    )


@app.get("/api/memory/{namespace}/search")
async def memory_namespace_search(
    namespace: str, query: str = "", tags: str | None = None
):
    tag_list = tags.split(",") if tags else None
    return get_memory_sharing().search(namespace, query=query, tags=tag_list)


# ── Main ──────────────────────────────────────────────────────────

def main():
    import uvicorn
    uvicorn.run("web.server:app", host="127.0.0.1", port=8080, reload=True)


if __name__ == "__main__":
    main()
