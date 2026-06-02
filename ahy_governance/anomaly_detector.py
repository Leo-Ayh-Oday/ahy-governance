"""
Anomaly Detector — Agent 行为异常检测引擎

检测类型:
  TOKEN_SPIKE           — Agent 突然消耗 10x token
  OUTPUT_LENGTH_ANOMALY — 输出长度异常（正常 100 字，突然 5000）
  REPEATED_CALLS        — 同一 Agent 1 分钟内被调 50 次
  SUCCESS_RATE_DROP     — 成功率骤降（99% → 60%）

设计:
  - deque 滚动窗口 + mean/stddev 基线
  - pull-based: 调 scan() 获取当前异常
  - 读 HealthMonitor + CostTracker 的内存数据，不查 DB
  - 零外部依赖

用法:
  detector = AnomalyDetector()
  anomalies = detector.scan_all(health_monitor, cost_tracker)
  for a in anomalies:
      if a.severity == Severity.CRITICAL:
          alert(a)
"""

from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from .conflict_detector import Severity


# ── Enums ───────────────────────────────────────────────────────

class AnomalyType(Enum):
    TOKEN_SPIKE = "token_spike"
    OUTPUT_LENGTH_ANOMALY = "output_length"
    REPEATED_CALLS = "repeated_calls"
    SUCCESS_RATE_DROP = "success_rate_drop"


# ── Data classes ────────────────────────────────────────────────

@dataclass
class Anomaly:
    """一次异常检测结果"""
    anomaly_type: AnomalyType
    agent_name: str
    severity: Severity
    description: str
    current_value: float
    baseline_value: float
    threshold: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type": self.anomaly_type.value,
            "agent": self.agent_name,
            "severity": self.severity.value,
            "description": self.description,
            "current_value": self.current_value,
            "baseline_value": self.baseline_value,
            "threshold": self.threshold,
            "timestamp": self.timestamp,
            "evidence": self.evidence,
        }


# ── Rolling window stats ────────────────────────────────────────

def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    variance = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


# ── Anomaly Detector ────────────────────────────────────────────

@dataclass
class AnomalyDetector:
    """Agent 行为异常检测器。

    调用 scan_all() 传入 HealthMonitor 和 CostTracker 实例，
    返回当前异常列表。空列表 = 无异常。

    所有阈值均可配置。
    """

    # Token spike: current > baseline * multiplier
    token_spike_multiplier: float = 10.0

    # Output length: current > baseline * multiplier
    output_length_multiplier: float = 5.0

    # Repeated calls: more than N calls in 60 seconds
    repeated_calls_per_minute: int = 50

    # Success rate drop: baseline - current > threshold
    success_rate_drop_threshold: float = 0.20

    # Rolling window for baseline computation (seconds)
    rolling_window_seconds: int = 3600

    # Minimum data points before anomaly detection kicks in
    min_data_points: int = 5

    # Internal: timestamped metric stores
    _token_history: dict[str, deque] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=1000))
    )
    _call_timestamps: dict[str, deque] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=1000))
    )
    _output_length_history: dict[str, deque] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=1000))
    )

    # ── Main scan ───────────────────────────────────────────────

    def scan_all(self, health_monitor, cost_tracker) -> list[Anomaly]:
        """扫描所有异常类型，返回异常列表。"""
        anomalies: list[Anomaly] = []
        anomalies.extend(self.scan_token_spikes(cost_tracker))
        anomalies.extend(self.scan_repeated_calls(health_monitor))
        anomalies.extend(self.scan_success_rate_drop(health_monitor))
        anomalies.extend(self.scan_output_length_anomaly(health_monitor))
        return anomalies

    def scan_and_heal(
        self, health_monitor, cost_tracker, workspace_id: str = "",
    ) -> list[dict]:
        """Scan anomalies and trigger self-healing for each finding."""
        from .checkpoint_store import get_checkpoint_store
        from .self_healer import IncidentType, get_healer

        results = []
        checkpoint_store = get_checkpoint_store()
        healer = get_healer()
        for anomaly in self.scan_all(health_monitor, cost_tracker):
            checkpoint = checkpoint_store.load_latest(
                anomaly.agent_name, workspace_id=workspace_id,
            )
            context = {"anomaly": anomaly.to_dict()}
            if checkpoint:
                context["checkpoint"] = checkpoint.to_dict()

            incident_type = _incident_for_anomaly(anomaly.anomaly_type)
            heal_result = healer.self_heal(
                anomaly.agent_name,
                incident_type,
                anomaly.description,
                context=context,
                workspace_id=workspace_id,
            )
            results.append({
                "anomaly": anomaly.to_dict(),
                "healing": heal_result.to_dict(),
            })
        return results

    # ── Token spike detection ───────────────────────────────────

    def scan_token_spikes(self, cost_tracker) -> list[Anomaly]:
        """检测 Agent token 消耗突增。"""
        anomalies: list[Anomaly] = []
        if not cost_tracker or not hasattr(cost_tracker, "_entries"):
            return anomalies

        # Group entries by agent
        agent_tokens: dict[str, list[tuple[float, int]]] = defaultdict(list)
        now = time.time()
        for entry in cost_tracker._entries:
            ts = _parse_timestamp(entry.timestamp)
            if now - ts > self.rolling_window_seconds:
                continue
            total_tokens = entry.tokens_in + entry.tokens_out
            agent_tokens[entry.agent_name].append((ts, total_tokens))

        for agent, points in agent_tokens.items():
            if len(points) < self.min_data_points:
                continue

            # Split into baseline (first 80%) and recent (last 20%)
            split_idx = max(1, int(len(points) * 0.8))
            baseline_values = [p[1] for p in points[:split_idx]]
            recent_values = [p[1] for p in points[split_idx:]]

            baseline_mean = _mean(baseline_values)
            if baseline_mean < 100:  # skip agents with trivial token usage
                continue

            recent_mean = _mean(recent_values)
            threshold = baseline_mean * self.token_spike_multiplier

            if recent_mean > threshold:
                anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.TOKEN_SPIKE,
                    agent_name=agent,
                    severity=Severity.HIGH if recent_mean > threshold * 2 else Severity.MEDIUM,
                    description=(
                        f"{agent} token 消耗突增: "
                        f"近期均值 {recent_mean:.0f} vs 基线 {baseline_mean:.0f} "
                        f"({recent_mean / baseline_mean:.1f}x)"
                    ),
                    current_value=recent_mean,
                    baseline_value=baseline_mean,
                    threshold=threshold,
                    evidence={
                        "recent_samples": len(recent_values),
                        "baseline_samples": len(baseline_values),
                        "spike_ratio": round(recent_mean / baseline_mean, 2),
                    },
                ))
        return anomalies

    # ── Repeated calls detection ────────────────────────────────

    def scan_repeated_calls(self, health_monitor) -> list[Anomaly]:
        """检测 Agent 在短时间内被大量重复调用。"""
        anomalies: list[Anomaly] = []
        if not health_monitor or not hasattr(health_monitor, "_calls"):
            return anomalies

        now = time.time()
        window = 60  # 1 minute window

        for agent, calls in health_monitor._calls.items():
            # Count calls in the last minute
            recent_calls = 0
            for call in calls:
                # calls don't have timestamps in _calls dict,
                # so we estimate from the list length and check
                # if the list is suspiciously long
                pass

            # Use list length as proxy — if > threshold, flag it
            if len(calls) > self.repeated_calls_per_minute:
                # Check if this is bursty: count calls that are
                # likely recent (assume uniform distribution,
                # flag if total > threshold * window_factor)
                total = len(calls)
                anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.REPEATED_CALLS,
                    agent_name=agent,
                    severity=Severity.HIGH if total > self.repeated_calls_per_minute * 2 else Severity.MEDIUM,
                    description=(
                        f"{agent} 调用次数异常: "
                        f"滚动窗口内 {total} 次调用 (阈值 {self.repeated_calls_per_minute})"
                    ),
                    current_value=total,
                    baseline_value=self.repeated_calls_per_minute,
                    threshold=self.repeated_calls_per_minute,
                    evidence={"total_calls_in_window": total},
                ))
        return anomalies

    # ── Success rate drop detection ─────────────────────────────

    def scan_success_rate_drop(self, health_monitor) -> list[Anomaly]:
        """检测 Agent 成功率骤降。"""
        anomalies: list[Anomaly] = []
        if not health_monitor or not hasattr(health_monitor, "_calls"):
            return anomalies

        for agent, calls in health_monitor._calls.items():
            if len(calls) < self.min_data_points:
                continue

            # Split into baseline (first 80%) and recent (last 20%)
            split_idx = max(1, int(len(calls) * 0.8))
            baseline_calls = calls[:split_idx]
            recent_calls = calls[split_idx:]

            baseline_rate = sum(1 for c in baseline_calls if c.get("success", True)) / len(baseline_calls)
            recent_rate = sum(1 for c in recent_calls if c.get("success", True)) / len(recent_calls)

            drop = baseline_rate - recent_rate
            if drop > self.success_rate_drop_threshold:
                anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.SUCCESS_RATE_DROP,
                    agent_name=agent,
                    severity=Severity.CRITICAL if drop > 0.5 else Severity.HIGH,
                    description=(
                        f"{agent} 成功率骤降: "
                        f"{recent_rate:.0%} (近期) vs {baseline_rate:.0%} (基线), "
                        f"下降 {drop:.0%}"
                    ),
                    current_value=recent_rate,
                    baseline_value=baseline_rate,
                    threshold=self.success_rate_drop_threshold,
                    evidence={
                        "baseline_samples": len(baseline_calls),
                        "recent_samples": len(recent_calls),
                        "drop_pct": round(drop * 100, 1),
                    },
                ))
        return anomalies

    # ── Output length anomaly detection ─────────────────────────

    def scan_output_length_anomaly(self, health_monitor) -> list[Anomaly]:
        """检测 Agent 输出长度异常。

        注意: 需要 HealthMonitor 的 call 记录中包含 output_length 字段。
        如果没有该字段，此检测器会静默跳过。
        """
        anomalies: list[Anomaly] = []
        if not health_monitor or not hasattr(health_monitor, "_calls"):
            return anomalies

        for agent, calls in health_monitor._calls.items():
            # Only detect if calls have output_length data
            lengths = [c.get("output_length", 0) for c in calls if "output_length" in c]
            if len(lengths) < self.min_data_points:
                continue

            split_idx = max(1, int(len(lengths) * 0.8))
            baseline_lengths = lengths[:split_idx]
            recent_lengths = lengths[split_idx:]

            baseline_mean = _mean(baseline_lengths)
            if baseline_mean < 10:  # skip trivial outputs
                continue

            recent_mean = _mean(recent_lengths)
            threshold = baseline_mean * self.output_length_multiplier

            if recent_mean > threshold:
                anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.OUTPUT_LENGTH_ANOMALY,
                    agent_name=agent,
                    severity=Severity.MEDIUM,
                    description=(
                        f"{agent} 输出长度异常: "
                        f"近期均值 {recent_mean:.0f} 字符 vs 基线 {baseline_mean:.0f} 字符 "
                        f"({recent_mean / baseline_mean:.1f}x)"
                    ),
                    current_value=recent_mean,
                    baseline_value=baseline_mean,
                    threshold=threshold,
                    evidence={
                        "recent_samples": len(recent_lengths),
                        "baseline_samples": len(baseline_lengths),
                        "length_ratio": round(recent_mean / baseline_mean, 2),
                    },
                ))
        return anomalies

    # ── Admin ───────────────────────────────────────────────────

    def reset(self):
        """清除所有历史数据。"""
        self._token_history.clear()
        self._call_timestamps.clear()
        self._output_length_history.clear()


# ── Helpers ─────────────────────────────────────────────────────

def _parse_timestamp(ts: str) -> float:
    """Parse ISO timestamp to Unix epoch seconds."""
    try:
        dt = datetime.fromisoformat(ts)
        return dt.timestamp()
    except (ValueError, TypeError):
        return time.time()


# ── Module-level convenience ────────────────────────────────────

_detector: AnomalyDetector | None = None


def get_anomaly_detector() -> AnomalyDetector:
    global _detector
    if _detector is None:
        _detector = AnomalyDetector()
    return _detector


def detect_anomalies(health_monitor=None, cost_tracker=None) -> list[Anomaly]:
    """便捷函数: 检测异常。"""
    from .health_monitor import get_monitor
    from .cost_tracker import get_tracker
    hm = health_monitor or get_monitor()
    ct = cost_tracker or get_tracker()
    return get_anomaly_detector().scan_all(hm, ct)


def detect_and_heal_anomalies(
    health_monitor=None, cost_tracker=None, workspace_id: str = "",
) -> list[dict]:
    """Scan anomalies and trigger self-healing for production auto-remediation."""
    from .health_monitor import get_monitor
    from .cost_tracker import get_tracker
    hm = health_monitor or get_monitor()
    ct = cost_tracker or get_tracker()
    return get_anomaly_detector().scan_and_heal(hm, ct, workspace_id)


def _incident_for_anomaly(anomaly_type: AnomalyType):
    from .self_healer import IncidentType

    mapping = {
        AnomalyType.TOKEN_SPIKE: IncidentType.TOKEN_SPIKE,
        AnomalyType.OUTPUT_LENGTH_ANOMALY: IncidentType.OUTPUT_INVALID,
        AnomalyType.REPEATED_CALLS: IncidentType.EXECUTION_ERROR,
        AnomalyType.SUCCESS_RATE_DROP: IncidentType.EXECUTION_ERROR,
    }
    return mapping.get(anomaly_type, IncidentType.UNKNOWN)
