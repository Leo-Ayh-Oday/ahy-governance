"""Ahy Governance — Multi-Agent Governance Platform.

Conflict Detection, Cost Tracking, Audit Logging for AI Agent deployments.
"""

from .conflict_detector import (
    ConflictDetector,
    Conflict,
    ConflictType,
    Severity,
    check_conflicts,
    get_detector,
)

__version__ = "0.1.0"
__all__ = [
    "ConflictDetector",
    "Conflict",
    "ConflictType",
    "Severity",
    "check_conflicts",
    "get_detector",
]
