"""
RBAC + API Key 管理 — 三级权限/密钥生命周期/多租户隔离

特性:
  三级角色: ADMIN / OPERATOR / VIEWER
  细粒度权限模型 (10 种 Permission)
  API Key 生命周期: generate → validate → rotate → revoke
  多租户工作空间隔离
  SHA-256 密钥哈希存储 (raw key 仅生成时返回一次)

用法:
  am = AccessManager()
  ws = am.create_workspace("my-workspace", "owner-id")
  am.add_user(ws.workspace_id, "user-1", Role.ADMIN)
  api_key, raw = am.create_api_key(ws.workspace_id, "user-1", "prod-key", Role.ADMIN)
  valid = am.check_permission(raw, Permission.AGENT_MANAGE)
"""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .storage import Database


# ── Enums ───────────────────────────────────────────────────────

class Role(Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class Permission(Enum):
    # Conflict Detection
    CONFLICT_READ = "conflict_read"
    CONFLICT_RESOLVE = "conflict_resolve"
    # Cost Tracking
    COST_READ = "cost_read"
    BUDGET_MANAGE = "budget_manage"
    # Audit
    AUDIT_READ = "audit_read"
    AUDIT_EXPORT = "audit_export"
    # Health
    HEALTH_READ = "health_read"
    AGENT_MANAGE = "agent_manage"
    # Admin
    WORKSPACE_MANAGE = "workspace_manage"
    APIKEY_MANAGE = "apikey_manage"


# Role → Permissions mapping
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: set(Permission),
    Role.OPERATOR: {
        Permission.CONFLICT_READ,
        Permission.CONFLICT_RESOLVE,
        Permission.COST_READ,
        Permission.AUDIT_READ,
        Permission.AUDIT_EXPORT,
        Permission.HEALTH_READ,
        Permission.AGENT_MANAGE,
    },
    Role.VIEWER: {
        Permission.CONFLICT_READ,
        Permission.COST_READ,
        Permission.AUDIT_READ,
        Permission.HEALTH_READ,
    },
}


# ── Data classes ────────────────────────────────────────────────

@dataclass
class Workspace:
    workspace_id: str
    name: str
    owner_user_id: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "workspace_id": self.workspace_id,
            "name": self.name,
            "owner_user_id": self.owner_user_id,
            "created_at": self.created_at,
            "user_count": 0,  # set externally
        }


@dataclass
class User:
    user_id: str
    role: Role
    workspace_id: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "role": self.role.value,
            "workspace_id": self.workspace_id,
            "created_at": self.created_at,
        }


@dataclass
class ApiKey:
    key_id: str
    key_hash: str
    name: str
    role: Role
    workspace_id: str
    created_at: str
    expires_at: str | None
    revoked: bool = False
    last_used: str | None = None

    def to_dict(self) -> dict:
        return {
            "key_id": self.key_id,
            "name": self.name,
            "role": self.role.value,
            "workspace_id": self.workspace_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "revoked": self.revoked,
            "last_used": self.last_used,
            "key_prefix": self.key_hash[:8] + "...",
        }


# ── Helpers ─────────────────────────────────────────────────────

def _generate_key_id() -> str:
    return secrets.token_hex(8)


def _generate_workspace_id() -> str:
    return secrets.token_hex(8)


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def _generate_raw_key() -> str:
    return "ahy_" + secrets.token_hex(20)  # ahy_ + 40 hex = 44 chars


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── AccessManager ───────────────────────────────────────────────

class AccessManager:
    def __init__(self, db: Database | None = None):
        self._db = db
        self._workspaces: dict[str, Workspace] = {}          # id → Workspace
        self._workspace_names: dict[str, str] = {}           # name → id
        self._users: dict[str, dict[str, User]] = {}         # workspace_id → {user_id → User}
        self._api_keys: dict[str, ApiKey] = {}               # key_id → ApiKey
        self._key_hashes: dict[str, str] = {}                # hash → key_id
        # Hydrate from DB
        if self._use_db:
            for row in self._db.workspace_all():
                ws = Workspace(workspace_id=row["workspace_id"], name=row["name"],
                               owner_user_id=row["owner_user_id"], created_at=row["created_at"])
                self._workspaces[ws.workspace_id] = ws
                self._workspace_names[ws.name] = ws.workspace_id
                self._users[ws.workspace_id] = {}
            for row in self._db.workspace_all():
                for u in self._db.rbac_users_by_workspace(row["workspace_id"]):
                    user = User(user_id=u["user_id"], role=Role(u["role"]),
                                workspace_id=u["workspace_id"], created_at=u["created_at"])
                    self._users[u["workspace_id"]][u["user_id"]] = user
            for row in self._db.apikeys_by_workspace("*"):
                apikeys = self._db.apikeys_by_workspace(row["workspace_id"])
                for k in apikeys:
                    if not isinstance(k, dict):
                        continue
                break
            # Load all non-revoked keys
            if self._db:
                for ws_row in self._db.workspace_all():
                    for k in self._db.apikeys_by_workspace(ws_row["workspace_id"]):
                        ak = ApiKey(key_id=k["key_id"], key_hash=k["key_hash"], name=k["name"],
                                    role=Role(k["role"]), workspace_id=k["workspace_id"],
                                    created_at=k["created_at"], expires_at=k["expires_at"],
                                    revoked=bool(k["revoked"]), last_used=k["last_used"])
                        self._api_keys[ak.key_id] = ak
                        self._key_hashes[ak.key_hash] = ak.key_id

    @property
    def _use_db(self) -> bool:
        return self._db is not None and self._db.enabled

    # ── Static helpers ────────────────────────────────────────

    @staticmethod
    def get_role_permissions(role: Role) -> set[Permission]:
        return ROLE_PERMISSIONS.get(role, set())

    @staticmethod
    def role_has_permission(role: Role, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS.get(role, set())

    # ── Workspace ─────────────────────────────────────────────

    def create_workspace(self, name: str, owner_user_id: str) -> Workspace:
        if name in self._workspace_names:
            raise ValueError(f"Workspace '{name}' already exists")
        ws_id = _generate_workspace_id()
        now = _utc_now()
        ws = Workspace(workspace_id=ws_id, name=name, owner_user_id=owner_user_id, created_at=now)
        self._workspaces[ws_id] = ws
        self._workspace_names[name] = ws_id
        self._users[ws_id] = {}
        if self._use_db:
            self._db.workspace_insert(ws_id, name, owner_user_id, now)
        return ws

    def get_workspace(self, name_or_id: str) -> Workspace | None:
        if self._use_db:
            row = self._db.workspace_get(name_or_id)
            if row:
                return Workspace(workspace_id=row["workspace_id"], name=row["name"],
                                 owner_user_id=row["owner_user_id"], created_at=row["created_at"])
            return None
        if name_or_id in self._workspace_names:
            name_or_id = self._workspace_names[name_or_id]
        return self._workspaces.get(name_or_id)

    def list_workspaces(self) -> list[Workspace]:
        return list(self._workspaces.values())

    # ── Users ─────────────────────────────────────────────────

    def add_user(self, workspace_id: str, user_id: str, role: Role) -> User:
        if workspace_id not in self._workspaces and not (self._use_db and self._db.workspace_get(workspace_id)):
            raise ValueError(f"Workspace not found: {workspace_id}")
        now = _utc_now()
        user = User(user_id=user_id, role=role, workspace_id=workspace_id, created_at=now)
        self._users.setdefault(workspace_id, {})[user_id] = user
        if self._use_db:
            self._db.rbac_user_insert(user_id, workspace_id, role.value, now)
        return user

    def get_users(self, workspace_id: str) -> list[User]:
        return list(self._users.get(workspace_id, {}).values())

    def update_user_role(self, workspace_id: str, user_id: str, role: Role) -> bool:
        ws_users = self._users.get(workspace_id, {})
        if user_id not in ws_users:
            return False
        ws_users[user_id].role = role
        return True

    def remove_user(self, workspace_id: str, user_id: str) -> bool:
        ws_users = self._users.get(workspace_id, {})
        if user_id not in ws_users:
            return False
        del ws_users[user_id]
        return True

    # ── API Keys ──────────────────────────────────────────────

    def create_api_key(
        self, workspace_id: str, user_id: str, name: str,
        role: Role, expires_in_days: int | None = None,
    ) -> tuple[ApiKey, str]:
        raw = _generate_raw_key()
        key_hash = _hash_key(raw)
        key_id = _generate_key_id()

        expires_at = None
        if expires_in_days is not None:
            expires_at = (
                datetime.now(timezone.utc) + timedelta(days=expires_in_days)
            ).isoformat()

        now = _utc_now()
        api_key = ApiKey(
            key_id=key_id, key_hash=key_hash, name=name,
            role=role, workspace_id=workspace_id,
            created_at=now, expires_at=expires_at,
        )
        self._api_keys[key_id] = api_key
        self._key_hashes[key_hash] = key_id
        if self._use_db:
            self._db.apikey_insert(key_id, key_hash, name, role.value, workspace_id, now, expires_at)
        return api_key, raw

    def validate_api_key(self, raw: str) -> ApiKey | None:
        key_hash = _hash_key(raw)
        now = _utc_now()
        if self._use_db:
            row = self._db.apikey_get_by_hash(key_hash)
            if row is None or row["revoked"]:
                return None
            if row["expires_at"]:
                try:
                    exp = datetime.fromisoformat(row["expires_at"])
                    if datetime.now(timezone.utc) > exp:
                        return None
                except (ValueError, TypeError):
                    pass
            self._db.apikey_update_last_used(key_hash, now)
            return ApiKey(key_id=row["key_id"], key_hash=row["key_hash"], name=row["name"],
                          role=Role(row["role"]), workspace_id=row["workspace_id"],
                          created_at=row["created_at"], expires_at=row["expires_at"],
                          revoked=bool(row["revoked"]), last_used=now)
        # In-memory path
        key_id = self._key_hashes.get(key_hash)
        if key_id is None:
            return None
        api_key = self._api_keys[key_id]
        if api_key.revoked:
            return None
        if api_key.expires_at:
            try:
                exp = datetime.fromisoformat(api_key.expires_at)
                if datetime.now(timezone.utc) > exp:
                    return None
            except (ValueError, TypeError):
                pass
        api_key.last_used = now
        return api_key

    def revoke_api_key(self, key_id: str) -> bool:
        api_key = self._api_keys.get(key_id)
        if api_key is None or api_key.revoked:
            return False
        api_key.revoked = True
        if self._use_db:
            self._db.apikey_revoke(key_id)
        return True

    def rotate_api_key(self, key_id: str) -> tuple[ApiKey, str] | None:
        old = self._api_keys.get(key_id)
        if old is None or old.revoked:
            return None
        old.revoked = True
        if self._use_db:
            self._db.apikey_revoke(key_id)
        return self.create_api_key(old.workspace_id, "", old.name, old.role)

    def get_api_keys(self, workspace_id: str) -> list[ApiKey]:
        if self._use_db:
            rows = self._db.apikeys_by_workspace(workspace_id)
            return [ApiKey(key_id=r["key_id"], key_hash=r["key_hash"], name=r["name"],
                           role=Role(r["role"]), workspace_id=r["workspace_id"],
                           created_at=r["created_at"], expires_at=r["expires_at"],
                           revoked=bool(r["revoked"]), last_used=r["last_used"]) for r in rows]
        return [
            k for k in self._api_keys.values()
            if k.workspace_id == workspace_id and not k.revoked
        ]

    # ── Permission Check ──────────────────────────────────────

    def check_permission(self, raw_key: str, permission: Permission) -> bool:
        api_key = self.validate_api_key(raw_key)
        if api_key is None:
            return False
        return permission in ROLE_PERMISSIONS.get(api_key.role, set())

    # ── Admin ─────────────────────────────────────────────────

    def reset(self):
        self._workspaces.clear()
        self._workspace_names.clear()
        self._users.clear()
        self._api_keys.clear()
        self._key_hashes.clear()
        if self._use_db:
            self._db.clear_all()


# ── Module-level convenience ────────────────────────────────────

_access_manager: AccessManager | None = None
_db: Database | None = None


def set_database(db: Database | None):
    global _db, _access_manager
    _db = db
    _access_manager = None


def get_access_manager() -> AccessManager:
    global _access_manager, _db
    if _access_manager is None:
        if _db is None:
            db_path = os.environ.get("AHY_DB_PATH", "")
            if db_path:
                from .storage import Database
                _db = Database(db_path)
        _access_manager = AccessManager(db=_db)
    return _access_manager
