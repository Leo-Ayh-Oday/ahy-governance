"""
Webhook Alerts — 实时告警推送（企业微信 / 钉钉 / 飞书 / Slack）

特性:
  企业微信 Bot (Markdown)
  钉钉 Bot (Markdown + @mention)
  飞书 Bot (Interactive Card)
  Slack Incoming Webhook
  全局告警路由 (按 severity 分发不同渠道)
  告警去重 (同类型告警 N 秒内不重复发送)

用法:
  alerter = AlertManager()
  alerter.add_channel("ops", "wecom", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx")
  alerter.send("ops", "Agent Planner is UNHEALTHY", "warning")
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.request

from .interfaces import NotifyChannel as NotifyChannelABC
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .storage import Database


# ── Alert ──────────────────────────────────────────────────────

@dataclass
class Alert:
    title: str
    body: str
    severity: str          # critical, high, warning, info
    source: str = ""       # agent_name or module
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_markdown(self) -> str:
        emoji = {"critical": "🔴", "high": "🟠", "warning": "🟡", "info": "🔵"}
        e = emoji.get(self.severity, "")
        return f"{e} **{self.title}**\n\n{self.body}\n\n> 来源: {self.source} | 时间: {self.timestamp}"


# ── Webhook Channels ───────────────────────────────────────────

class WebhookChannel(NotifyChannelABC):
    """Base class for webhook channels."""

    def __init__(self, url: str, secret: str | None = None):
        self.url = url
        self.secret = secret

    def send(self, alert: Alert) -> bool:
        raise NotImplementedError

    def _post(self, payload: dict) -> bool:
        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                self.url, data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return 200 <= resp.status < 300
        except Exception:
            return False


class WecomBot(WebhookChannel):
    """企业微信群机器人 (Markdown 格式)."""

    def send(self, alert: Alert) -> bool:
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": alert.to_markdown(),
            },
        }
        return self._post(payload)


class DingtalkBot(WebhookChannel):
    """钉钉群机器人 (Markdown + @all for critical)."""

    def send(self, alert: Alert) -> bool:
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": alert.title,
                "text": alert.to_markdown(),
            },
        }
        if alert.severity in ("critical", "high"):
            payload["at"] = {"isAtAll": True}
        return self._post(payload)


class FeishuBot(WebhookChannel):
    """飞书群机器人 (Interactive Card)."""

    def send(self, alert: Alert) -> bool:
        color_map = {"critical": "red", "high": "orange", "warning": "yellow", "info": "blue"}
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": alert.title},
                    "template": color_map.get(alert.severity, "blue"),
                },
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": alert.body}},
                    {"tag": "hr"},
                    {
                        "tag": "note",
                        "elements": [
                            {"tag": "plain_text", "content": f"来源: {alert.source} | {alert.timestamp}"}
                        ],
                    },
                ],
            },
        }
        if self.secret:
            timestamp = str(int(time.time()))
            sign = self._feishu_sign(timestamp)
            payload["timestamp"] = timestamp
            payload["sign"] = sign
        return self._post(payload)

    def _feishu_sign(self, timestamp: str) -> str:
        string_to_sign = f"{timestamp}\n{self.secret}"
        h = hmac.new(string_to_sign.encode(), digestmod=hashlib.sha256)
        return h.hexdigest()


class SlackWebhook(WebhookChannel):
    """Slack Incoming Webhook."""

    def send(self, alert: Alert) -> bool:
        color = {"critical": "#ef4444", "high": "#f59e0b", "warning": "#f59e0b", "info": "#3b82f6"}
        payload = {
            "attachments": [
                {
                    "color": color.get(alert.severity, "#3b82f6"),
                    "title": alert.title,
                    "text": alert.body,
                    "footer": f"ahyops | {alert.source}",
                }
            ]
        }
        return self._post(payload)


# ── Alert Manager ──────────────────────────────────────────────

CHANNEL_CLASSES = {
    "wecom": WecomBot,
    "dingtalk": DingtalkBot,
    "feishu": FeishuBot,
    "slack": SlackWebhook,
}


@dataclass
class ChannelConfig:
    name: str
    kind: str            # wecom / dingtalk / feishu / slack
    url: str
    secret: str | None = None
    min_severity: str = "warning"  # only send >= this level


class AlertAggregator:
    """告警聚合器：智能分组、去重、升级策略。

    - CRITICAL → 立即推送
    - HIGH     → 每小时汇总推送一次
    - MEDIUM/LOW → 每日摘要中汇总
    - 已自动修复 → 降级为 info，仅在摘要中提及
    """

    def __init__(self, window_minutes: int = 60):
        self._sent: dict[str, float] = {}       # dedup_key → last_sent
        self._pending: dict[str, list[Alert]] = {}  # severity → queued alerts
        self._window = window_minutes * 60

    def should_send(self, alert: Alert) -> bool:
        """Return False if this alert should be suppressed (dedup / auto-resolved)."""
        if alert.severity == "info":
            return False  # info always goes to digest only
        key = alert.source or alert.title
        now = time.time()
        if key in self._sent and (now - self._sent[key]) < self._window:
            return False
        return True

    def route(self, alert: Alert) -> str:
        """Return routing target: 'push' | 'digest_hourly' | 'digest_daily' | 'silent'."""
        if alert.severity == "critical":
            return "push"
        if alert.severity == "high":
            return "digest_hourly"
        return "digest_daily"

    def mark_sent(self, alert: Alert):
        key = alert.source or alert.title
        self._sent[key] = time.time()

    def reset(self):
        self._sent.clear()
        self._pending.clear()


class AlertManager:
    def __init__(self, db: Database | None = None):
        self._db = db
        self._channels: dict[str, list[tuple[ChannelConfig, WebhookChannel]]] = {}
        self._sent_cache: dict[str, float] = {}    # dedup key → timestamp
        self._dedup_seconds: float = 3600           # 1 hour dedup window (was 5 min)
        self._aggregator = AlertAggregator(window_minutes=60)
        self._maintenance_until: float = 0          # maintenance window end time
        self._stats: dict[str, int] = {"sent": 0, "suppressed": 0, "auto_resolved": 0}
        # Hydrate from DB
        if self._use_db:
            for row in self._db.alert_channels_all():
                cls = CHANNEL_CLASSES.get(row["kind"])
                if cls:
                    group = row["group_name"]
                    config = ChannelConfig(name=row["name"], kind=row["kind"], url=row["url"],
                                           secret=row["secret"], min_severity=row["min_severity"])
                    channel = cls(row["url"], row["secret"])
                    self._channels.setdefault(group, []).append((config, channel))

    @property
    def _use_db(self) -> bool:
        return self._db is not None and self._db.enabled

    # ── Channel management ──────────────────────────────────

    def add_channel(
        self, group: str, kind: str, url: str,
        secret: str | None = None, min_severity: str = "warning",
    ):
        cls = CHANNEL_CLASSES.get(kind)
        if cls is None:
            raise ValueError(f"Unknown channel kind '{kind}'. Use: {list(CHANNEL_CLASSES)}")
        config = ChannelConfig(name=f"{group}-{kind}", kind=kind, url=url,
                               secret=secret, min_severity=min_severity)
        channel = cls(url, secret)
        self._channels.setdefault(group, []).append((config, channel))
        if self._use_db:
            self._db.alert_channel_insert(group, config.name, kind, url, secret, min_severity)

    def remove_group(self, group: str):
        self._channels.pop(group, None)
        if self._use_db:
            self._db.alert_channel_delete_group(group)

    # ── Sending ──────────────────────────────────────────────

    def send(
        self, group: str, title: str, body: str = "",
        severity: str = "warning", source: str = "",
        dedup_key: str | None = None,
        auto_resolved: bool = False,
    ) -> int:
        """Send alert to all channels in a group. Returns count of channels sent to."""
        if group not in self._channels:
            return 0

        # Auto-resolved: downgrade severity
        if auto_resolved:
            severity = "info"
            title = f"✅ 已自动处理: {title}"

        alert = Alert(title=title, body=body, severity=severity, source=source)
        key = dedup_key or f"{group}:{title}"

        # Dedup via aggregator
        if not self._aggregator.should_send(alert):
            self._stats["suppressed"] += 1
            return 0

        # Maintenance window: suppress non-critical
        if self.in_maintenance() and severity not in ("critical",):
            self._stats["suppressed"] += 1
            return 0

        severity_order = {"info": 0, "warning": 1, "high": 2, "critical": 3}
        min_level = severity_order.get(severity, 0)

        # Routing: only push if aggregator says "push"
        route = self._aggregator.route(alert)
        if route != "push":
            # Queue for digest instead of immediate delivery
            self._aggregator._pending.setdefault(route, []).append(alert)
            return 0

        sent = 0
        for config, channel in self._channels[group]:
            if severity_order.get(config.min_severity, 0) > min_level:
                continue
            if channel.send(alert):
                sent += 1

        if sent > 0:
            self._sent_cache[key] = time.time()
            self._aggregator.mark_sent(alert)
            self._stats["sent"] += sent

        return sent

    # ── Maintenance window ───────────────────────────────────

    def set_maintenance_window(self, duration_minutes: int = 60):
        """Suppress non-critical alerts for the given duration."""
        self._maintenance_until = time.time() + duration_minutes * 60

    def clear_maintenance_window(self):
        self._maintenance_until = 0

    def in_maintenance(self) -> bool:
        return time.time() < self._maintenance_until

    # ── Auto-resolve tracking ────────────────────────────────

    def mark_auto_resolved(self, title: str, source: str = ""):
        """Record that an issue was auto-resolved by the system."""
        self._stats["auto_resolved"] += 1

    def get_stats(self) -> dict:
        return dict(self._stats)

    # ── Convenience senders ──────────────────────────────────

    def send_budget_warning(self, usage_pct: float, limit_usd: float, current_usd: float):
        self.send(
            "ops",
            title=f"AI 预算告警 — 已使用 {usage_pct:.1f}%",
            body=f"本月预算: ${limit_usd:.2f}\n已花费: ${current_usd:.2f}\n剩余: ${limit_usd - current_usd:.2f}",
            severity="warning",
            source="cost_tracker",
            dedup_key="budget_warning",
        )

    def send_agent_unhealthy(self, agent_name: str, status: str, success_rate: float):
        self.send(
            "ops",
            title=f"Agent {agent_name} 状态异常 — {status}",
            body=f"Agent: {agent_name}\n状态: {status}\n成功率: {success_rate:.1%}",
            severity="critical" if status in ("unhealthy", "offline") else "high",
            source=agent_name,
            dedup_key=f"agent_unhealthy:{agent_name}",
        )

    def send_conflict_detected(self, agents: list[str], description: str, severity: str):
        self.send(
            "ops",
            title=f"Agent 冲突检测 — {severity}",
            body=f"涉及 Agent: {', '.join(agents)}\n\n{description}",
            severity=severity.lower() if severity.lower() in ("critical", "high", "warning") else "warning",
            source="conflict_detector",
            dedup_key=f"conflict:{':'.join(sorted(agents))}",
        )

    def send_prompt_injection(self, agent_name: str, confidence: float):
        self.send(
            "security",
            title=f"检测到 Prompt 注入攻击",
            body=f"Agent: {agent_name}\n置信度: {confidence:.2f}\n\n用户输入可能包含恶意指令，已被标记。",
            severity="high",
            source="prompt_guard",
            dedup_key=f"injection:{agent_name}",
        )

    # ── Admin ──────────────────────────────────────────────────

    def list_channels(self) -> dict:
        result = {}
        for group, channels in self._channels.items():
            result[group] = [{"name": c.name, "kind": c.kind, "min_severity": c.min_severity} for c, _ in channels]
        return result

    def clear_cache(self):
        self._sent_cache.clear()


# ── Module-level convenience ──────────────────────────────────

_alerter: AlertManager | None = None


_db: Database | None = None


def set_database(db: Database | None):
    global _db, _alerter
    _db = db
    _alerter = None


def get_alerter() -> AlertManager:
    global _alerter, _db
    if _alerter is None:
        if _db is None:
            db_path = os.environ.get("AHY_DB_PATH", "")
            if db_path:
                from .storage import Database
                _db = Database(db_path)
        _alerter = AlertManager(db=_db)
    return _alerter
