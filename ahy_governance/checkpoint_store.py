"""
Checkpoint Store — Agent 运行状态持久化

在每次 Agent 执行前后保存状态快照，崩溃后可从 checkpoint 恢复现场，
让自愈后的 Agent 知道自己"做到哪了"，而不是从零开始。

用法:
  store = CheckpointStore()
  store.set_database(db)
  cid = store.save("Planner", "sess-123", {"step": 5, "progress": "60%"}))
  state = store.load_latest("Planner", "sess-123")
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Checkpoint:
    """单个 Agent 状态快照."""
    checkpoint_id: int = 0
    agent_name: str = ""
    session_id: str = ""
    state: dict = field(default_factory=dict)
    step: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "checkpoint_id": self.checkpoint_id,
            "agent_name": self.agent_name,
            "session_id": self.session_id,
            "state": self.state,
            "step": self.step,
            "created_at": self.created_at,
        }


class CheckpointStore:
    """Checkpoint 持久化管理器."""

    def __init__(self):
        self._db = None

    def set_database(self, db):
        self._db = db

    def save(
        self, agent_name: str, session_id: str, state: dict,
        step: str = "", workspace_id: str = "",
    ) -> int:
        """保存一个 checkpoint。返回 checkpoint_id。"""
        if not self._db or not self._db.enabled:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        return self._db.checkpoint_insert(
            agent_name=agent_name,
            session_id=session_id,
            state_json=json.dumps(state, ensure_ascii=False),
            step=step,
            created_at=now,
            workspace_id=workspace_id,
        )

    def load_latest(
        self, agent_name: str, session_id: str = "",
        workspace_id: str = "",
    ) -> Checkpoint | None:
        """加载最新的 checkpoint。"""
        if not self._db or not self._db.enabled:
            return None
        row = self._db.checkpoint_latest(agent_name, session_id, workspace_id)
        if row is None:
            return None
        return self._row_to_checkpoint(row)

    def list_checkpoints(
        self, agent_name: str = "", session_id: str = "",
        workspace_id: str = "", limit: int = 50,
    ) -> list[Checkpoint]:
        """列出 checkpoints。"""
        if not self._db or not self._db.enabled:
            return []
        rows = self._db.checkpoint_list(agent_name, session_id, workspace_id, limit)
        return [self._row_to_checkpoint(r) for r in rows]

    def prune(self, max_age_days: int = 7, workspace_id: str = "") -> int:
        """清理过期 checkpoint。返回删除数量。"""
        if not self._db or not self._db.enabled:
            return 0
        return self._db.checkpoint_prune(max_age_days, workspace_id)

    @staticmethod
    def _row_to_checkpoint(row: dict) -> Checkpoint:
        return Checkpoint(
            checkpoint_id=row.get("id", 0),
            agent_name=row.get("agent_name", ""),
            session_id=row.get("session_id", ""),
            state=json.loads(row.get("state_json", "{}")),
            step=row.get("step", ""),
            created_at=row.get("created_at", ""),
        )


# ── Module-level convenience ────────────────────────────────────

_store: CheckpointStore | None = None


def get_checkpoint_store() -> CheckpointStore:
    global _store
    if _store is None:
        _store = CheckpointStore()
    return _store


def save_checkpoint(
    agent_name: str, session_id: str, state: dict,
    step: str = "", workspace_id: str = "",
) -> int:
    return get_checkpoint_store().save(agent_name, session_id, state, step, workspace_id)


def load_checkpoint(
    agent_name: str, session_id: str = "", workspace_id: str = "",
) -> Checkpoint | None:
    return get_checkpoint_store().load_latest(agent_name, session_id, workspace_id)
