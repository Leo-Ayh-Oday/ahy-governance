"""Ahy Governance — Multi-Agent Governance Platform.

Conflict Detection, Cost Tracking, Audit Logging, Health Monitoring, RBAC, Prompt Guard for AI Agent deployments.
"""

from .conflict_detector import (
    ConflictDetector,
    Conflict,
    ConflictType,
    Severity,
    check_conflicts,
    get_detector,
)
from .semantic_conflict import SemanticConflictDetector, SemanticResult
from .events import (
    AgentStartEvent,
    AgentEndEvent,
    LLMCallEvent,
    LLMResultEvent,
    ToolStartEvent,
    ToolEndEvent,
    AgentErrorEvent,
)
from .collector import GovernanceCollector, GovernancePipeline
from .cost_tracker import (
    CostTracker,
    CostEntry,
    BudgetConfig,
    BudgetExceededError,
    ModelPricing,
    track_cost,
    get_tracker,
    DEFAULT_PRICING,
)
from .audit_logger import (
    AuditReporter,
    AuditEntry,
    AuditEventType,
    get_auditor,
    log_audit,
)
from .health_monitor import (
    HealthMonitor,
    AgentMetrics,
    AgentStatus,
    Heartbeat,
    get_monitor,
    check_health,
)
from .rbac import (
    AccessManager,
    Role,
    Permission,
    ApiKey,
    Workspace,
    User,
    get_access_manager,
)
from .prompt_guard import (
    PromptGuard,
    InjectionResult,
    MaskResult,
    SanitizeResult,
    get_guard,
    sanitize_prompt,
)

from .memory_sharing import (
    MemorySharing,
    MemoryEntry,
    get_memory_sharing,
    shared_memory_write,
    shared_memory_read,
)

from .auth import AuthManager, get_auth

# ── SDK Decorator ───────────────────────────────────────────────
from .decorator import track

# ── Anomaly Detector ────────────────────────────────────────────
from .anomaly_detector import (
    AnomalyDetector,
    Anomaly,
    AnomalyType,
    get_anomaly_detector,
    detect_anomalies,
)

# ── Auto Resolver ───────────────────────────────────────────────
from .auto_resolver import (
    AutoResolver,
    Resolution,
    ResolutionStatus,
    ResolutionStrategy,
    get_resolver,
    auto_resolve,
)

# ── Cost Advisor ────────────────────────────────────────────────
from .cost_advisor import (
    CostAdvisor,
    Recommendation,
    RecommendationType,
    Priority,
    get_advisor,
    analyze_costs,
)

# ── Storage backends ────────────────────────────────────────────
from .storage import create_database, Database

# ── State store (Redis / in-memory) ─────────────────────────────
from .state_store import get_state_store

# ── Structured logging ──────────────────────────────────────────
from .logging_config import setup_logging, get_logger

# ── Adapter registry ──────────────────────────────────────────
from .adapters import register_adapter, list_adapters, get_adapter

# ── Enterprise modules (optional) ────────────────────────────

try:
    from .compliance_reporter import ComplianceReporter, get_reporter
except ImportError:
    ComplianceReporter = None
    get_reporter = None

try:
    from .webhook_alerts import get_alerter
except ImportError:
    get_alerter = None

try:
    from .policy_engine import PolicyEngine, get_engine
except ImportError:
    PolicyEngine = None
    get_engine = None

__version__ = "0.9.0"
__all__ = [
    # Conflict Detector
    "ConflictDetector",
    "Conflict",
    "ConflictType",
    "Severity",
    "check_conflicts",
    "get_detector",
    # Semantic Conflict
    "SemanticConflictDetector",
    "SemanticResult",
    # Framework Adapters
    "GovernanceCollector",
    "GovernancePipeline",
    "AgentStartEvent",
    "AgentEndEvent",
    "LLMCallEvent",
    "LLMResultEvent",
    "ToolStartEvent",
    "ToolEndEvent",
    "AgentErrorEvent",
    "register_adapter",
    "list_adapters",
    "get_adapter",
    # Cost Tracker
    "CostTracker",
    "CostEntry",
    "BudgetConfig",
    "BudgetExceededError",
    "ModelPricing",
    "track_cost",
    "get_tracker",
    "DEFAULT_PRICING",
    # Audit Reporter
    "AuditReporter",
    "AuditEntry",
    "AuditEventType",
    "get_auditor",
    "log_audit",
    # Health Monitor
    "HealthMonitor",
    "AgentMetrics",
    "AgentStatus",
    "Heartbeat",
    "get_monitor",
    "check_health",
    # RBAC
    "AccessManager",
    "Role",
    "Permission",
    "ApiKey",
    "Workspace",
    "User",
    "get_access_manager",
    # Prompt Guard
    "PromptGuard",
    "InjectionResult",
    "MaskResult",
    "SanitizeResult",
    "get_guard",
    "sanitize_prompt",
    # Memory Sharing
    "MemorySharing",
    "MemoryEntry",
    "get_memory_sharing",
    "shared_memory_write",
    "shared_memory_read",
    # Storage & Infrastructure
    "create_database",
    "Database",
    "get_state_store",
    "setup_logging",
    "get_logger",
    # Anomaly Detector
    "AnomalyDetector",
    "Anomaly",
    "AnomalyType",
    "get_anomaly_detector",
    "detect_anomalies",
    # Auto Resolver
    "AutoResolver",
    "Resolution",
    "ResolutionStatus",
    "ResolutionStrategy",
    "get_resolver",
    "auto_resolve",
    # SDK Decorator
    "track",
    # Cost Advisor
    "CostAdvisor",
    "Recommendation",
    "RecommendationType",
    "Priority",
    "get_advisor",
    "analyze_costs",
    # Enterprise
    "ComplianceReporter",
    "get_reporter",
    "get_alerter",
    "PolicyEngine",
    "get_engine",
]