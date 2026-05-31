"""
Schema migration — ensures workspace_id columns exist on legacy tables.

Safe to run on new or old databases. For existing v0 tables without
workspace_id, drops and recreates them (data loss acceptable for v0.7→v1.0).
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .storage import Database


def ensure_schema(db: Database) -> None:
    """Ensure DB has current schema. Called once in init_database().

    Strategy: if legacy tables exist without workspace_id composite PKs,
    drop operational tables and let _init_tables recreate them.
    RBAC tables are preserved.
    """
    if not db.enabled:
        return

    # Check if health_heartbeats has the old single-PK schema
    try:
        row = db._fetchone("PRAGMA table_info(health_heartbeats)")
        # If table doesn't exist yet, _init_tables will create it correctly
    except Exception:
        return

    # Check if workspace_id column exists (new schema has it in PK)
    cols = db._fetchall("PRAGMA table_info(health_heartbeats)")
    col_names = [c["name"] for c in cols] if cols else []

    if "workspace_id" not in col_names:
        _migrate_operational_tables(db)


def _migrate_operational_tables(db: Database) -> None:
    """Drop old operational tables so _init_tables recreates them with workspace_id."""
    tables = [
        "health_heartbeats", "health_calls",
        "health_pipelines", "health_pipeline_steps",
        "cost_entries", "cost_pricing", "cost_budget",
        "conflicts", "audit_entries",
        "memory_entries", "alert_channels",
    ]
    for t in tables:
        db._execute(f"DROP TABLE IF EXISTS {t}")


def ensure_conflicts_schema(db: Database) -> None:
    """Add resolution columns to conflicts table if they don't exist (pre-v1.1 upgrade)."""
    if not db.enabled:
        return
    try:
        cols = db._fetchall("PRAGMA table_info(conflicts)")
        col_names = [c["name"] for c in cols] if cols else []
        for col, defn in [
            ("resolution_status", "TEXT NOT NULL DEFAULT 'open'"),
            ("resolution_type", "TEXT DEFAULT ''"),
            ("resolved_by", "TEXT DEFAULT ''"),
            ("resolution_note", "TEXT DEFAULT ''"),
            ("resolved_at", "TEXT DEFAULT ''"),
        ]:
            if col not in col_names:
                db._execute(f"ALTER TABLE conflicts ADD COLUMN {col} {defn}")
    except Exception:
        return
