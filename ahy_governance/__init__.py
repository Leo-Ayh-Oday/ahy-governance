"""Ahy Governance — Multi-Agent Governance Platform.

Conflict Detection, Cost Tracking, Audit Logging, Health Monitoring, RBAC for AI Agent deployments.
"""

from .conflict_detector import (
    ConflictDetector,
    Conflict,
    ConflictType,
    Severity,
    check_conflicts,
    get_detector,
)
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

__version__ = "0.5.0"
__all__ = [
    # Conflict Detector
    "ConflictDetector",
    "Conflict",
    "ConflictType",
    "Severity",
    "check_conflicts",
    "get_detector",
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
]