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
    detect_and_heal_anomalies,
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

# ── Self Healer ────────────────────────────────────────────────
from .self_healer import (
    SelfHealer,
    SelfHealLevel,
    RecoveryActionType,
    IncidentType,
    RecoveryAction,
    RecoveryRule,
    RecoveryLedgerEntry,
    HealResult,
    RuleEngine,
    LLMDoctor,
    RecoveryLedger,
    RecoveryStatus,
    get_healer,
    self_heal,
)
from .recovery_rules import default_recovery_rules
from .llm_diagnose import make_deepseek_diagnose_fn
from .recovery_learner import RecoveryLearner, LearnResult, get_learner, scan_and_learn
from .checkpoint_store import (
    CheckpointStore, Checkpoint, get_checkpoint_store,
    save_checkpoint, load_checkpoint,
)
from .evaluator import (
    EvalRegistry, EvalScore, EvalCase, EvalRun, EvalSummary,
    Scorer, CodeScorer, LLMScorer,
    get_eval_registry, run_eval,
    make_builtin_llm_scorers,
)
from .output_guard import (
    OutputGuard, GuardPolicy, GuardVerdict, GuardResult,
    GuardBlockedError, GuardAction, GuardTiming,
    get_output_guard,
)
from .policy_catalog import default_policies
from .quality_gate import QualityGate, GateConfig, GateResult, run_quality_gate
from .agent_discovery import AgentDiscovery, DiscoveredAgent, get_discovery, scan_local_agents

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
    from .policy_engine import (
        PolicyEngine,
        get_policy_engine,
        AgentLevel,
        RiskClass,
        AgentCapabilities,
        GovernanceStrategy,
        evaluate_agent_level,
        recommend_strategy,
        AGENT_LEVEL_STRATEGIES,
    )
except ImportError:
    PolicyEngine = None
    get_policy_engine = None
    AgentLevel = None
    RiskClass = None
    AgentCapabilities = None
    GovernanceStrategy = None
    evaluate_agent_level = None
    recommend_strategy = None
    AGENT_LEVEL_STRATEGIES = None

__version__ = "0.9.1"
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
    "detect_and_heal_anomalies",
    # Auto Resolver
    "AutoResolver",
    "Resolution",
    "ResolutionStatus",
    "ResolutionStrategy",
    "get_resolver",
    "auto_resolve",
    # Self Healer
    "SelfHealer",
    "SelfHealLevel",
    "RecoveryActionType",
    "IncidentType",
    "RecoveryAction",
    "RecoveryRule",
    "RecoveryLedgerEntry",
    "HealResult",
    "RuleEngine",
    "LLMDoctor",
    "RecoveryLedger",
    "RecoveryStatus",
    "get_healer",
    "self_heal",
    "default_recovery_rules",
    "make_deepseek_diagnose_fn",
    "RecoveryLearner",
    "LearnResult",
    "get_learner",
    "scan_and_learn",
    "CheckpointStore",
    "Checkpoint",
    "get_checkpoint_store",
    "save_checkpoint",
    "load_checkpoint",
    "EvalRegistry",
    "EvalScore",
    "EvalCase",
    "EvalRun",
    "EvalSummary",
    "Scorer",
    "CodeScorer",
    "LLMScorer",
    "get_eval_registry",
    "run_eval",
    "make_builtin_llm_scorers",
    "OutputGuard",
    "GuardPolicy",
    "GuardVerdict",
    "GuardResult",
    "GuardBlockedError",
    "GuardAction",
    "GuardTiming",
    "get_output_guard",
    "default_policies",
    "QualityGate",
    "GateConfig",
    "GateResult",
    "run_quality_gate",
    "AgentDiscovery",
    "DiscoveredAgent",
    "get_discovery",
    "scan_local_agents",
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
    # Policy Engine + Agent Level Grading
    "PolicyEngine",
    "get_policy_engine",
    "AgentLevel",
    "RiskClass",
    "AgentCapabilities",
    "GovernanceStrategy",
    "evaluate_agent_level",
    "recommend_strategy",
    "AGENT_LEVEL_STRATEGIES",
]
