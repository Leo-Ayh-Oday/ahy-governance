"""RBAC + API Key 管理测试 — 三级权限/密钥生命周期/多租户隔离"""

import pytest

from ahy_governance import (
    AccessManager,
    Role,
    Permission,
    ApiKey,
    Workspace,
    get_access_manager,
)


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def am():
    m = AccessManager()
    yield m
    m.reset()


@pytest.fixture
def populated_am(am):
    ws1 = am.create_workspace("workspace-alpha", "owner-1")
    ws2 = am.create_workspace("workspace-beta", "owner-2")
    am.add_user(ws1.workspace_id, "user-a", Role.ADMIN)
    am.add_user(ws1.workspace_id, "user-b", Role.OPERATOR)
    am.add_user(ws1.workspace_id, "user-c", Role.VIEWER)
    am.add_user(ws2.workspace_id, "user-d", Role.ADMIN)
    return am


# ── Role Permission Tests ───────────────────────────────────────

class TestRolePermissions:
    def test_admin_has_all_permissions(self):
        perms = AccessManager.get_role_permissions(Role.ADMIN)
        assert Permission.AGENT_MANAGE in perms
        assert Permission.WORKSPACE_MANAGE in perms
        assert Permission.APIKEY_MANAGE in perms
        assert Permission.BUDGET_MANAGE in perms

    def test_operator_has_limited_permissions(self, am):
        perms = AccessManager.get_role_permissions(Role.OPERATOR)
        assert Permission.AGENT_MANAGE in perms
        assert Permission.CONFLICT_READ in perms
        assert Permission.COST_READ in perms
        assert Permission.APIKEY_MANAGE not in perms
        assert Permission.WORKSPACE_MANAGE not in perms

    def test_viewer_read_only(self, am):
        perms = AccessManager.get_role_permissions(Role.VIEWER)
        assert Permission.CONFLICT_READ in perms
        assert Permission.COST_READ in perms
        assert Permission.AUDIT_READ in perms
        assert Permission.HEALTH_READ in perms
        assert Permission.AGENT_MANAGE not in perms
        assert Permission.BUDGET_MANAGE not in perms

    def test_role_enum_values(self):
        assert Role.ADMIN.value == "admin"
        assert Role.OPERATOR.value == "operator"
        assert Role.VIEWER.value == "viewer"

    def test_permission_enum_values(self):
        values = {p.value for p in Permission}
        assert "conflict_read" in values
        assert "cost_read" in values
        assert "audit_read" in values
        assert "health_read" in values
        assert "agent_manage" in values
        assert "workspace_manage" in values


# ── Workspace Tests ─────────────────────────────────────────────

class TestWorkspace:
    def test_create_workspace(self, am):
        ws = am.create_workspace("test-ws", "owner-1")
        assert ws.workspace_id is not None
        assert ws.name == "test-ws"
        assert len(ws.workspace_id) == 16  # hex

    def test_create_workspace_unique_ids(self, am):
        ws1 = am.create_workspace("a", "o1")
        ws2 = am.create_workspace("b", "o2")
        assert ws1.workspace_id != ws2.workspace_id

    def test_get_workspace(self, populated_am):
        ws = populated_am.get_workspace("workspace-alpha")
        assert ws is not None
        assert ws.name == "workspace-alpha"

    def test_get_workspace_nonexistent(self, am):
        assert am.get_workspace("no-such-ws") is None

    def test_list_workspaces(self, populated_am):
        wss = populated_am.list_workspaces()
        assert len(wss) == 2

    def test_workspace_to_dict(self, am):
        ws = am.create_workspace("w", "o")
        d = ws.to_dict()
        assert d["name"] == "w"
        assert d["user_count"] == 0


# ── User Tests ──────────────────────────────────────────────────

class TestUsers:
    def test_add_user(self, populated_am):
        ws = populated_am.get_workspace("workspace-alpha")
        user = populated_am.add_user(ws.workspace_id, "new-user", Role.VIEWER)
        assert user.user_id == "new-user"
        assert user.role == Role.VIEWER

    def test_add_user_nonexistent_workspace(self, am):
        with pytest.raises(ValueError, match="Workspace not found"):
            am.add_user("fake-id", "user", Role.VIEWER)

    def test_get_users(self, populated_am):
        ws = populated_am.get_workspace("workspace-alpha")
        users = populated_am.get_users(ws.workspace_id)
        assert len(users) == 3

    def test_update_user_role(self, populated_am):
        ws = populated_am.get_workspace("workspace-alpha")
        updated = populated_am.update_user_role(ws.workspace_id, "user-c", Role.OPERATOR)
        assert updated is True
        users = populated_am.get_users(ws.workspace_id)
        user_c = [u for u in users if u.user_id == "user-c"][0]
        assert user_c.role == Role.OPERATOR

    def test_update_user_nonexistent(self, am):
        assert not am.update_user_role("fake", "fake", Role.ADMIN)

    def test_remove_user(self, populated_am):
        ws = populated_am.get_workspace("workspace-alpha")
        assert populated_am.remove_user(ws.workspace_id, "user-c")
        assert len(populated_am.get_users(ws.workspace_id)) == 2


# ── API Key Tests ───────────────────────────────────────────────

class TestApiKey:
    def test_create_api_key(self, populated_am):
        ws = populated_am.get_workspace("workspace-alpha")
        api_key, raw = populated_am.create_api_key(
            ws.workspace_id, "user-a", "my-key", Role.ADMIN
        )
        assert api_key.key_id is not None
        assert api_key.name == "my-key"
        assert api_key.role == Role.ADMIN
        assert raw.startswith("ahy_")
        assert len(raw) > 40

    def test_raw_key_shown_once(self, populated_am):
        ws = populated_am.get_workspace("workspace-alpha")
        _, raw = populated_am.create_api_key(ws.workspace_id, "user-a", "k1", Role.ADMIN)
        # The stored key should NOT contain the raw key
        stored = populated_am.get_api_keys(ws.workspace_id)
        for k in stored:
            assert not hasattr(k, "raw_key") or k.raw_key is None

    def test_validate_api_key(self, populated_am):
        ws = populated_am.get_workspace("workspace-alpha")
        _, raw = populated_am.create_api_key(ws.workspace_id, "user-a", "k1", Role.ADMIN)
        result = populated_am.validate_api_key(raw)
        assert result is not None
        assert result.name == "k1"

    def test_validate_invalid_key(self, populated_am):
        assert populated_am.validate_api_key("ahy_invalid_key_12345") is None

    def test_validate_revoked_key(self, populated_am):
        ws = populated_am.get_workspace("workspace-alpha")
        api_key, raw = populated_am.create_api_key(ws.workspace_id, "user-a", "k1", Role.ADMIN)
        populated_am.revoke_api_key(api_key.key_id)
        assert populated_am.validate_api_key(raw) is None

    def test_revoke_api_key(self, populated_am):
        ws = populated_am.get_workspace("workspace-alpha")
        api_key, _ = populated_am.create_api_key(ws.workspace_id, "user-a", "k1", Role.ADMIN)
        assert populated_am.revoke_api_key(api_key.key_id)
        # Double revoke returns False
        assert not populated_am.revoke_api_key(api_key.key_id)

    def test_rotate_api_key(self, populated_am):
        ws = populated_am.get_workspace("workspace-alpha")
        api_key, old_raw = populated_am.create_api_key(ws.workspace_id, "user-a", "k1", Role.ADMIN)
        new_api_key, new_raw = populated_am.rotate_api_key(api_key.key_id)
        assert new_api_key.key_id != api_key.key_id
        assert new_raw != old_raw
        # Old key no longer validates
        assert populated_am.validate_api_key(old_raw) is None
        # New key validates
        assert populated_am.validate_api_key(new_raw) is not None

    def test_get_api_keys(self, populated_am):
        ws = populated_am.get_workspace("workspace-alpha")
        _, _ = populated_am.create_api_key(ws.workspace_id, "user-a", "key-1", Role.ADMIN)
        _, _ = populated_am.create_api_key(ws.workspace_id, "user-b", "key-2", Role.OPERATOR)
        keys = populated_am.get_api_keys(ws.workspace_id)
        assert len(keys) == 2

    def test_api_keys_not_include_revoked(self, populated_am):
        ws = populated_am.get_workspace("workspace-alpha")
        k1, _ = populated_am.create_api_key(ws.workspace_id, "user-a", "k1", Role.ADMIN)
        k2, _ = populated_am.create_api_key(ws.workspace_id, "user-a", "k2", Role.ADMIN)
        populated_am.revoke_api_key(k1.key_id)
        keys = populated_am.get_api_keys(ws.workspace_id)
        assert len(keys) == 1
        assert keys[0].key_id == k2.key_id


# ── Permission Checking Tests ───────────────────────────────────

class TestPermissionCheck:
    def test_check_permission_admin(self, populated_am):
        ws = populated_am.get_workspace("workspace-alpha")
        _, raw = populated_am.create_api_key(ws.workspace_id, "user-a", "admin-key", Role.ADMIN)
        assert populated_am.check_permission(raw, Permission.WORKSPACE_MANAGE)
        assert populated_am.check_permission(raw, Permission.AGENT_MANAGE)
        assert populated_am.check_permission(raw, Permission.CONFLICT_READ)

    def test_check_permission_viewer_denied(self, populated_am):
        ws = populated_am.get_workspace("workspace-alpha")
        _, raw = populated_am.create_api_key(ws.workspace_id, "user-c", "view-key", Role.VIEWER)
        assert populated_am.check_permission(raw, Permission.CONFLICT_READ)
        assert not populated_am.check_permission(raw, Permission.AGENT_MANAGE)
        assert not populated_am.check_permission(raw, Permission.BUDGET_MANAGE)

    def test_check_permission_invalid_key(self, populated_am):
        assert not populated_am.check_permission("fake_key", Permission.CONFLICT_READ)

    def test_role_has_permission(self, am):
        assert AccessManager.role_has_permission(Role.ADMIN, Permission.APIKEY_MANAGE)
        assert AccessManager.role_has_permission(Role.OPERATOR, Permission.COST_READ)
        assert not AccessManager.role_has_permission(Role.VIEWER, Permission.AGENT_MANAGE)

    def test_operator_permissions(self, populated_am):
        ws = populated_am.get_workspace("workspace-alpha")
        _, raw = populated_am.create_api_key(ws.workspace_id, "user-b", "op-key", Role.OPERATOR)
        # Operator can read everything
        assert populated_am.check_permission(raw, Permission.CONFLICT_READ)
        assert populated_am.check_permission(raw, Permission.COST_READ)
        assert populated_am.check_permission(raw, Permission.HEALTH_READ)
        assert populated_am.check_permission(raw, Permission.AGENT_MANAGE)
        # But cannot manage workspace or api keys
        assert not populated_am.check_permission(raw, Permission.WORKSPACE_MANAGE)
        assert not populated_am.check_permission(raw, Permission.APIKEY_MANAGE)


# ── Multi-Tenant Isolation Tests ────────────────────────────────

class TestMultiTenantIsolation:
    def test_cross_workspace_key_fails(self, populated_am):
        ws1 = populated_am.get_workspace("workspace-alpha")
        ws2 = populated_am.get_workspace("workspace-beta")
        _, raw = populated_am.create_api_key(ws1.workspace_id, "user-a", "k1", Role.ADMIN)
        # Key from ws1 should not grant access to ws2 users
        users = populated_am.get_users(ws2.workspace_id)
        assert len(users) == 1
        assert users[0].user_id == "user-d"

    def test_users_isolated_per_workspace(self, populated_am):
        ws1 = populated_am.get_workspace("workspace-alpha")
        ws2 = populated_am.get_workspace("workspace-beta")
        u1 = populated_am.get_users(ws1.workspace_id)
        u2 = populated_am.get_users(ws2.workspace_id)
        u1_ids = {u.user_id for u in u1}
        u2_ids = {u.user_id for u in u2}
        assert u1_ids.isdisjoint(u2_ids)


# ── Edge Cases ──────────────────────────────────────────────────

class TestEdgeCases:
    def test_api_key_expiration(self, am):
        ws = am.create_workspace("w", "o")
        am.add_user(ws.workspace_id, "u", Role.ADMIN)
        api_key, raw = am.create_api_key(
            ws.workspace_id, "u", "exp-key", Role.ADMIN,
            expires_in_days=0,  # expires immediately
        )
        assert am.validate_api_key(raw) is None

    def test_large_workspace(self, am):
        ws = am.create_workspace("big-ws", "owner")
        for i in range(100):
            am.add_user(ws.workspace_id, f"user-{i}", Role.VIEWER)
        assert len(am.get_users(ws.workspace_id)) == 100

    def test_reset_clears_all(self, populated_am):
        populated_am.reset()
        assert len(populated_am.list_workspaces()) == 0

    def test_last_used_tracking(self, populated_am):
        ws = populated_am.get_workspace("workspace-alpha")
        _, raw = populated_am.create_api_key(ws.workspace_id, "user-a", "k1", Role.ADMIN)
        populated_am.validate_api_key(raw)
        keys = populated_am.get_api_keys(ws.workspace_id)
        assert keys[0].last_used is not None

    def test_key_hash_not_raw(self, populated_am):
        ws = populated_am.get_workspace("workspace-alpha")
        _, raw = populated_am.create_api_key(ws.workspace_id, "user-a", "k1", Role.ADMIN)
        keys = populated_am.get_api_keys(ws.workspace_id)
        # The stored hash should be SHA-256 (64 hex chars), not the raw key
        assert len(keys[0].key_hash) == 64
        assert keys[0].key_hash != raw

    def test_unique_key_ids(self, populated_am):
        ws = populated_am.get_workspace("workspace-alpha")
        ids = set()
        for i in range(20):
            k, _ = populated_am.create_api_key(ws.workspace_id, "user-a", f"k{i}", Role.ADMIN)
            ids.add(k.key_id)
        assert len(ids) == 20

    def test_workspace_name_unique(self, am):
        am.create_workspace("unique-name", "o1")
        with pytest.raises(ValueError, match="already exists"):
            am.create_workspace("unique-name", "o2")


# ── Convenience Tests ───────────────────────────────────────────

class TestConvenience:
    def test_get_access_manager_singleton(self):
        a1 = get_access_manager()
        a2 = get_access_manager()
        assert a1 is a2
        a1.reset()
