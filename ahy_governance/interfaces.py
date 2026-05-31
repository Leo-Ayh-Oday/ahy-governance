"""
Plugin interfaces for ahy-governance.

All extension points are defined as Abstract Base Classes. Community contributors
implement these interfaces to add custom detectors, notification channels, and
cost-tracking strategies without modifying core code.

Scaffold a new plugin:
    python -m ahy_governance scaffold --type=detector --name=MyDetector
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


# ── Conflict Detection ─────────────────────────────────────────────

@dataclass
class ConflictResult:
    conflict_type: str
    agent_a: str
    agent_b: str
    severity: str       # "critical" | "high" | "medium" | "low"
    description: str
    suggestion: str
    auto_resolvable: bool = False


class ConflictDetector(ABC):
    """Conflict detection strategy interface.

    Implementations define HOW to detect conflicts between agent outputs.
    The engine calls detect() with the agent list and execution context.
    """

    @abstractmethod
    def detect(self, agents: list, context: dict) -> list[ConflictResult]:
        ...

    @abstractmethod
    def name(self) -> str:
        ...


# ── Notification Channels ──────────────────────────────────────────

class NotifyChannel(ABC):
    """Notification channel interface.

    Implementations define HOW alerts are delivered (WeChat, Feishu, Slack, etc.).
    The alerter calls send() for each alert routed to this channel.
    """

    @abstractmethod
    async def send(self, message: dict) -> bool:
        """Deliver an alert. Return True on success."""

    @abstractmethod
    def name(self) -> str:
        """Human-readable channel name, e.g. 'Feishu Bot'."""

    def health_check(self) -> bool:
        """Return True if the channel is reachable. Default: always healthy."""
        return True


# ── Cost Tracking ──────────────────────────────────────────────────

class CostTracker(ABC):
    """Cost tracking strategy interface.

    Implementations define HOW to estimate cost for LLM calls and whether
    to throttle based on budget constraints.
    """

    @abstractmethod
    def estimate(self, request: dict) -> float:
        """Estimate cost in USD for a single LLM request.

        request keys: model, tokens_in, tokens_out, provider
        """

    @abstractmethod
    def should_throttle(self, agent_id: str, budget_limit: float) -> bool:
        """Return True if the agent should be throttled due to budget."""

    @abstractmethod
    def name(self) -> str:
        ...


# ── Strategy Registry ──────────────────────────────────────────────

class StrategyRegistry:
    """Global registry for discoverable strategies.

    Community contributors register their implementations via
    Python entry_points (pyproject.toml) or programmatically.
    """

    _detectors: dict[str, type[ConflictDetector]] = {}
    _channels: dict[str, type[NotifyChannel]] = {}
    _trackers: dict[str, type[CostTracker]] = {}

    @classmethod
    def register_detector(cls, detector_cls: type[ConflictDetector]) -> None:
        instance = detector_cls()
        cls._detectors[instance.name()] = detector_cls

    @classmethod
    def register_channel(cls, channel_cls: type[NotifyChannel]) -> None:
        instance = channel_cls()
        cls._channels[instance.name()] = channel_cls

    @classmethod
    def register_tracker(cls, tracker_cls: type[CostTracker]) -> None:
        instance = tracker_cls()
        cls._trackers[instance.name()] = tracker_cls

    @classmethod
    def list_detectors(cls) -> list[str]:
        return sorted(cls._detectors.keys())

    @classmethod
    def list_channels(cls) -> list[str]:
        return sorted(cls._channels.keys())

    @classmethod
    def list_trackers(cls) -> list[str]:
        return sorted(cls._trackers.keys())

    @classmethod
    def get_detector(cls, name: str) -> ConflictDetector | None:
        detector_cls = cls._detectors.get(name)
        return detector_cls() if detector_cls else None

    @classmethod
    def get_channel(cls, name: str) -> NotifyChannel | None:
        channel_cls = cls._channels.get(name)
        return channel_cls() if channel_cls else None

    @classmethod
    def get_tracker(cls, name: str) -> CostTracker | None:
        tracker_cls = cls._trackers.get(name)
        return tracker_cls() if tracker_cls else None


# ── Plugin discovery via entry_points ──────────────────────────────

def discover_plugins() -> int:
    """Load strategies registered via pyproject.toml entry_points.

    [project.entry-points."ahy_governance.detectors"]
    my_detector = "my_package:MyDetector"

    [project.entry-points."ahy_governance.channels"]
    dingtalk = "my_package:DingTalkChannel"

    Returns number of plugins loaded.
    """
    if not _has_entry_points():
        return 0
    count = 0
    for ep in _iter_entry_points(group="ahy_governance.detectors"):
        try:
            StrategyRegistry.register_detector(ep.load())
            count += 1
        except Exception:
            pass
    for ep in _iter_entry_points(group="ahy_governance.channels"):
        try:
            StrategyRegistry.register_channel(ep.load())
            count += 1
        except Exception:
            pass
    for ep in _iter_entry_points(group="ahy_governance.trackers"):
        try:
            StrategyRegistry.register_tracker(ep.load())
            count += 1
        except Exception:
            pass
    return count


def _has_entry_points() -> bool:
    try:
        from importlib.metadata import entry_points
        return True
    except ImportError:
        return False


def _iter_entry_points(group: str):
    try:
        from importlib.metadata import entry_points
        return entry_points(group=group)
    except Exception:
        return []
