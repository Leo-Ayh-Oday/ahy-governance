"""Tests for auth module — registration, login, JWT, API keys."""

import pytest
import os
import tempfile
from ahy_governance.auth import AuthManager, get_auth, _make_jwt, _verify_jwt


@pytest.fixture
def auth():
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()
    mgr = AuthManager(db.name)
    yield mgr
    try:
        os.unlink(db.name)
    except PermissionError:
        pass  # Windows SQLite file lock, temp dir will clean itself


class TestRegistration:
    def test_register_success(self, auth):
        user = auth.register("test@example.com", "password123")
        assert user["email"] == "test@example.com"
        assert "id" in user

    def test_register_duplicate_email(self, auth):
        auth.register("dup@example.com", "password123")
        with pytest.raises(ValueError, match="already registered"):
            auth.register("dup@example.com", "password456")

    def test_register_short_password(self, auth):
        with pytest.raises(ValueError, match="at least 6"):
            auth.register("a@b.com", "12345")

    def test_register_lowercases_email(self, auth):
        user = auth.register("Test@Example.COM", "password123")
        assert user["email"] == "test@example.com"


class TestLogin:
    def test_login_success(self, auth):
        auth.register("login@test.com", "mypassword")
        result = auth.login("login@test.com", "mypassword")
        assert "token" in result
        assert result["email"] == "login@test.com"

    def test_login_wrong_password(self, auth):
        auth.register("login@test.com", "correct")
        with pytest.raises(ValueError, match="Invalid email or password"):
            auth.login("login@test.com", "wrong")

    def test_login_nonexistent(self, auth):
        with pytest.raises(ValueError, match="Invalid email or password"):
            auth.login("nobody@nowhere.com", "anything")


class TestJWT:
    def test_roundtrip(self, auth):
        payload = {"sub": "user-123", "email": "a@b.com", "exp": 9999999999}
        token = _make_jwt(payload)
        decoded = _verify_jwt(token)
        assert decoded is not None
        assert decoded["sub"] == "user-123"

    def test_expired_token(self):
        payload = {"sub": "x", "exp": 1}  # 1970
        token = _make_jwt(payload)
        assert _verify_jwt(token) is None

    def test_tampered_token(self):
        payload = {"sub": "x", "exp": 9999999999}
        token = _make_jwt(payload)
        parts = token.split(".")
        tampered = parts[0] + "." + parts[1] + "." + "x" * 43
        assert _verify_jwt(tampered) is None

    def test_token_verify_integration(self, auth):
        auth.register("jwt@test.com", "pass123")
        result = auth.login("jwt@test.com", "pass123")
        user_id = auth.verify_token(result["token"])
        assert user_id is not None


class TestAPIKeys:
    def test_create_and_list(self, auth):
        user = auth.register("keys@test.com", "password123")
        key = auth.create_api_key(user["id"], "prod")
        assert key["raw_key"].startswith("ahy_")
        assert len(key["raw_key"]) == 4 + 48  # ahy_ + 48 hex

        keys = auth.list_api_keys(user["id"])
        assert len(keys) == 1
        assert keys[0]["name"] == "prod"

    def test_verify_api_key(self, auth):
        user = auth.register("verify@test.com", "password123")
        key = auth.create_api_key(user["id"], "test")
        user_id = auth.verify_api_key(key["raw_key"])
        assert user_id == user["id"]

    def test_verify_bad_key(self, auth):
        assert auth.verify_api_key("ahy_badbadbad") is None

    def test_delete_key(self, auth):
        user = auth.register("del@test.com", "password123")
        key = auth.create_api_key(user["id"])
        assert auth.delete_api_key(user["id"], key["id"]) is True
        assert auth.delete_api_key(user["id"], "nonexistent") is False

    def test_verify_deleted_key(self, auth):
        user = auth.register("delv@test.com", "password123")
        key = auth.create_api_key(user["id"])
        auth.delete_api_key(user["id"], key["id"])
        assert auth.verify_api_key(key["raw_key"]) is None


class TestAuthMiddlewareIntegration:
    """Simulate the middleware logic from server.py"""
    def test_valid_token_passes(self, auth):
        auth.register("mw@test.com", "password123")
        result = auth.login("mw@test.com", "password123")
        user_id = auth.verify_token(result["token"])
        assert user_id is not None

    def test_api_key_passes(self, auth):
        user = auth.register("apikey@test.com", "password123")
        key = auth.create_api_key(user["id"])
        user_id = auth.verify_api_key(key["raw_key"])
        assert user_id == user["id"]
