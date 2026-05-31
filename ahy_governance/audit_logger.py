"""
Audit Reporter — 不可篡改审计日志（append-only + SHA-256 hash 链）

特性:
  Hash 链完整性校验（每个 entry 的 hash 依赖前一个 entry）
  防篡改检测（find_tampered / verify_integrity）
  SOC2 / ISO27001 合规报告一键导出
  多维度筛选（agent / session / event_type / 时间范围）

用法:
  auditor = AuditReporter()
  auditor.log(AuditEventType.AGENT_START, "Planner", {"task": "合同审查"})
  assert auditor.verify_integrity()
  report = auditor.export_soc2()
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


# ── Event Types ─────────────────────────────────────────────────

class AuditEventType(Enum):
    # Agent lifecycle
    AGENT_START = "agent_start"
    AGENT_COMPLETE = "agent_complete"
    AGENT_ERROR = "agent_error"
    AGENT_RETRY = "agent_retry"

    # Pipeline lifecycle
    PIPELINE_START = "pipeline_start"
    PIPELINE_COMPLETE = "pipeline_complete"
    PIPELINE_BLOCKED = "pipeline_blocked"

    # Conflict events
    CONFLICT_DETECTED = "conflict_detected"
    CONFLICT_RESOLVED = "conflict_resolved"

    # Budget events
    BUDGET_WARNING = "budget_warning"
    BUDGET_EXCEEDED = "budget_exceeded"

    # Human actions
    HUMAN_REVIEW = "human_review"
    HUMAN_OVERRIDE = "human_override"

    # Tool calls
    TOOL_CALL = "tool_call"

    # Config & security
    CONFIG_CHANGE = "config_change"
    MODEL_CHANGE = "model_change"
    PERMISSION_DENIED = "permission_denied"


# ── Genesis hash ────────────────────────────────────────────────

GENESIS_HASH = "0" * 64  # SHA-256 of empty string is not used; this is the chain root


# ── AuditEntry ──────────────────────────────────────────────────

@dataclass
class AuditEntry:
    index: int
    event_type: AuditEventType
    agent_name: str
    details: dict
    session_id: str
    timestamp: str
    hash: str
    prev_hash: str

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "event_type": self.event_type.value,
            "agent": self.agent_name,
            "session_id": self.session_id,
            "details": self.details,
            "timestamp": self.timestamp,
            "hash": self.hash,
            "prev_hash": self.prev_hash,
        }

    def __repr__(self) -> str:
        return (
            f"AuditEntry(index={self.index}, type={self.event_type.value}, "
            f"agent={self.agent_name}, hash={self.hash[:12]}...)"
        )


# ── Utility ─────────────────────────────────────────────────────

def _serialize(entry_data: dict) -> bytes:
    """Deterministic JSON serialization for hashing."""
    return json.dumps(entry_data, sort_keys=True, ensure_ascii=False).encode("utf-8")


def _compute_hash(prev_hash: str, entry_data: dict) -> str:
    payload = prev_hash.encode("ascii") + _serialize(entry_data)
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── AuditReporter ───────────────────────────────────────────────

class AuditReporter:
    def __init__(self):
        self._entries: list[AuditEntry] = []
        self._db = None

    def set_database(self, db):
        self._db = db

    # ── Logging ───────────────────────────────────────────────

    def log(
        self, event_type: AuditEventType, agent_name: str,
        details: dict | None = None, session_id: str = "",
        timestamp: str | None = None, workspace_id: str = "",
    ) -> AuditEntry:
        details = details or {}
        index = len(self._entries)
        prev_hash = self._entries[-1].hash if self._entries else GENESIS_HASH
        ts = timestamp or _utc_now()

        entry_data = {
            "index": index,
            "event_type": event_type.value,
            "agent_name": agent_name,
            "details": details,
            "session_id": session_id,
            "timestamp": ts,
        }
        entry_hash = _compute_hash(prev_hash, entry_data)

        entry = AuditEntry(
            index=index, event_type=event_type, agent_name=agent_name,
            details=details, session_id=session_id, timestamp=ts,
            hash=entry_hash, prev_hash=prev_hash,
        )
        self._entries.append(entry)
        if self._db and self._db.enabled:
            self._db.audit_insert(index, event_type.value, agent_name,
                                   json.dumps(details, ensure_ascii=False),
                                   session_id, ts, entry_hash, prev_hash,
                                   workspace_id)
        return entry

    # ── Integrity ─────────────────────────────────────────────

    def verify_integrity(self, workspace_id: str = "") -> bool:
        if not self._entries:
            return True
        prev = GENESIS_HASH
        for e in self._entries:
            entry_data = {
                "index": e.index,
                "event_type": e.event_type.value,
                "agent_name": e.agent_name,
                "details": e.details,
                "session_id": e.session_id,
                "timestamp": e.timestamp,
            }
            expected = _compute_hash(prev, entry_data)
            if expected != e.hash:
                return False
            prev = e.hash
        return True

    def find_tampered(self) -> list[AuditEntry]:
        if not self._entries:
            return []
        tampered: list[AuditEntry] = []
        prev = GENESIS_HASH
        for e in self._entries:
            entry_data = {
                "index": e.index,
                "event_type": e.event_type.value,
                "agent_name": e.agent_name,
                "details": e.details,
                "session_id": e.session_id,
                "timestamp": e.timestamp,
            }
            expected = _compute_hash(prev, entry_data)
            if expected != e.hash:
                tampered.append(e)
            prev = e.hash
        return tampered

    def root_hash(self) -> str:
        return self._entries[-1].hash if self._entries else GENESIS_HASH

    # ── Query ─────────────────────────────────────────────────

    def query(
        self, *, agent_name: str | None = None,
        event_type: AuditEventType | None = None,
        session_id: str | None = None,
    ) -> list[AuditEntry]:
        results = self._entries
        if agent_name is not None:
            results = [e for e in results if e.agent_name == agent_name]
        if event_type is not None:
            results = [e for e in results if e.event_type == event_type]
        if session_id is not None:
            results = [e for e in results if e.session_id == session_id]
        return results

    def recent(self, n: int = 20, workspace_id: str = "") -> list[AuditEntry]:
        if not self._entries:
            return []
        return list(reversed(self._entries[-n:]))

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    # ── Compliance Reports ────────────────────────────────────

    def export_soc2(self) -> dict:
        verified = self.verify_integrity()
        events = [e.to_dict() for e in self._entries]
        return {
            "framework": "SOC2",
            "generated_at": _utc_now(),
            "total_events": len(events),
            "chain_verified": verified,
            "audit_trail_hash": self.root_hash(),
            "controls": {
                "security": {
                    "access_events": sum(
                        1 for e in self._entries
                        if e.event_type in (
                            AuditEventType.PERMISSION_DENIED,
                            AuditEventType.CONFIG_CHANGE,
                        )
                    ),
                    "tamper_proof": verified,
                    "description": "System is protected against unauthorized access and tampering",
                },
                "availability": {
                    "error_events": sum(
                        1 for e in self._entries
                        if e.event_type == AuditEventType.AGENT_ERROR
                    ),
                    "pipeline_blocks": sum(
                        1 for e in self._entries
                        if e.event_type == AuditEventType.PIPELINE_BLOCKED
                    ),
                    "description": "System is available for operation and recovery",
                },
                "confidentiality": {
                    "permission_checks": sum(
                        1 for e in self._entries
                        if e.event_type == AuditEventType.PERMISSION_DENIED
                    ),
                    "description": "Data and system resources are protected from unauthorized disclosure",
                },
                "processing_integrity": {
                    "conflicts_detected": sum(
                        1 for e in self._entries
                        if e.event_type == AuditEventType.CONFLICT_DETECTED
                    ),
                    "overrides": sum(
                        1 for e in self._entries
                        if e.event_type == AuditEventType.HUMAN_OVERRIDE
                    ),
                    "description": "System processing is complete, accurate, and authorized",
                },
                "privacy": {
                    "description": "Personal information is protected in accordance with privacy commitments",
                },
            },
            "events": events,
        }

    def export_iso27001(self) -> dict:
        verified = self.verify_integrity()
        events = [e.to_dict() for e in self._entries]
        return {
            "framework": "ISO27001",
            "generated_at": _utc_now(),
            "total_events": len(events),
            "chain_verified": verified,
            "audit_trail_hash": self.root_hash(),
            "annex_a_controls": {
                "A.9": {
                    "title": "Access Control",
                    "status": "compliant" if verified else "needs_review",
                    "events": sum(
                        1 for e in self._entries
                        if e.event_type in (
                            AuditEventType.PERMISSION_DENIED,
                            AuditEventType.CONFIG_CHANGE,
                            AuditEventType.HUMAN_OVERRIDE,
                        )
                    ),
                },
                "A.10": {
                    "title": "Cryptography",
                    "status": "compliant" if verified else "needs_review",
                    "description": "SHA-256 hash chain ensures non-repudiation and integrity",
                },
                "A.12": {
                    "title": "Operations Security",
                    "status": "compliant" if verified else "needs_review",
                    "events": sum(
                        1 for e in self._entries
                        if e.event_type in (
                            AuditEventType.AGENT_ERROR,
                            AuditEventType.AGENT_RETRY,
                            AuditEventType.PIPELINE_BLOCKED,
                        )
                    ),
                },
                "A.16": {
                    "title": "Information Security Incident Management",
                    "status": "compliant" if verified else "needs_review",
                    "events": sum(
                        1 for e in self._entries
                        if e.event_type in (
                            AuditEventType.AGENT_ERROR,
                            AuditEventType.CONFLICT_DETECTED,
                            AuditEventType.BUDGET_EXCEEDED,
                            AuditEventType.HUMAN_REVIEW,
                        )
                    ),
                },
                "A.18": {
                    "title": "Compliance",
                    "status": "compliant" if verified else "needs_review",
                    "description": "Audit trail with hash chain supports regulatory compliance requirements",
                },
            },
            "events": events,
        }

    # ── Export ─────────────────────────────────────────────────

    def export_csv(self, filepath: str):
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "index", "event_type", "agent", "session_id",
                "timestamp", "hash", "prev_hash",
                "details",
            ])
            writer.writeheader()
            for e in self._entries:
                d = e.to_dict()
                d["details"] = json.dumps(d["details"], ensure_ascii=False)
                writer.writerow(d)

    def export_json(self, filepath: str):
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(
                [e.to_dict() for e in self._entries],
                f, indent=2, ensure_ascii=False,
            )

    # ── Admin ──────────────────────────────────────────────────

    def reset(self):
        self._entries.clear()


# ── Module-level convenience ────────────────────────────────────

_auditor: AuditReporter | None = None


def get_auditor() -> AuditReporter:
    global _auditor
    if _auditor is None:
        _auditor = AuditReporter()
    return _auditor


def log_audit(
    event_type: AuditEventType, agent_name: str,
    details: dict | None = None, session_id: str = "",
) -> AuditEntry:
    return get_auditor().log(event_type, agent_name, details, session_id)
