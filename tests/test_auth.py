"""Tests for auth module — registration, login, JWT, API keys."""

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import pytest
import os
import tempfile
from base64 import urlsafe_b64encode
from ahy_governance.auth import (
    AuthManager, get_auth, _make_jwt, _verify_jwt,
    _hash_password, _verify_password, _hash_key, _b64, _b64_decode,
    JWT_SECRET, API_KEY_PREFIX,
)


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


# ── Password hashing edge cases ─────────────────────────────

class TestPasswordEdgeCases:
    def test_hash_and_verify_roundtrip(self):
        h = _hash_password("testpass")
        assert _verify_password("testpass", h) is True
        assert _verify_password("wrong", h) is False

    def test_legacy_sha256_format(self):
        salt = secrets.token_hex(16)
        h = hashlib.sha256(f"{salt}:legacy_pass".encode()).hexdigest()
        stored = f"{salt}:{h}"
        assert _verify_password("legacy_pass", stored) is True
        assert _verify_password("wrong", stored) is False

    def test_invalid_stored_format(self):
        assert _verify_password("pw", "no-colon-here") is False

    def test_hash_key_consistent(self):
        k1 = _hash_key("ahy_test123")
        k2 = _hash_key("ahy_test123")
        assert k1 == k2
        assert len(k1) == 64

    def test_bcrypt_fallback_without_bcrypt(self, monkeypatch):
        """When bcrypt not installed, _hash_password uses SHA-256."""
        import ahy_governance.auth as auth_mod
        monkeypatch.setattr(auth_mod, "_HAS_BCRYPT", False)
        h = _hash_password("test123")
        # Should be salt:hash format
        assert ":" in h
        assert _verify_password("test123", h) is True

    def test_verify_bcrypt_hash_without_bcrypt(self, monkeypatch):
        """When bcrypt hash exists but bcrypt not installed, returns False."""
        import ahy_governance.auth as auth_mod
        monkeypatch.setattr(auth_mod, "_HAS_BCRYPT", False)
        # A bcrypt hash
        assert _verify_password("pw", "$2b$12$abcdefghijklmnopqrstuuABCDEFGHIJKLMNOPQRSTUVWXYZ") is False

    def test_verify_bcrypt_hash_with_bcrypt(self):
        """When bcrypt is installed, bcrypt hashes should verify."""
        try:
            import bcrypt
        except ImportError:
            pytest.skip("bcrypt not installed")
        h = bcrypt.hashpw("test".encode(), bcrypt.gensalt()).decode()
        assert _verify_password("test", h) is True
        assert _verify_password("wrong", h) is False


# ── JWT edge cases ──────────────────────────────────────────

class TestJWTEdgeCases:
    def test_b64_roundtrip(self):
        data = b"hello world !@#$%"
        assert _b64_decode(_b64(data)) == data

    def test_make_and_verify(self):
        payload = {"sub": "u1", "exp": int(time.time()) + 3600}
        token = _make_jwt(payload)
        assert len(token.split(".")) == 3
        decoded = _verify_jwt(token)
        assert decoded["sub"] == "u1"

    def test_pyjwt_fallback_to_handrolled(self, monkeypatch):
        """When PyJWT fails with InvalidTokenError, try hand-rolled."""
        import ahy_governance.auth as auth_mod
        # Make pyjwt path fail with InvalidTokenError
        class FakePyjwt:
            class InvalidTokenError(Exception):
                pass
            class ExpiredSignatureError(Exception):
                pass
            @staticmethod
            def encode(payload, secret, algorithm):
                return "bad.token.format"
            @staticmethod
            def decode(token, secret, algorithms):
                raise FakePyjwt.InvalidTokenError("bad")
        monkeypatch.setattr(auth_mod, "_HAS_PYJWT", True)
        monkeypatch.setattr(auth_mod, "_pyjwt", FakePyjwt)
        # Should fall through to hand-rolled verification
        # Make a valid hand-rolled token
        header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        body = _b64(json.dumps({"sub": "test", "exp": int(time.time()) + 3600}).encode())
        sig = _b64(hmac.new(JWT_SECRET.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest())
        token = f"{header}.{body}.{sig}"
        decoded = _verify_jwt(token)
        assert decoded is not None
        assert decoded["sub"] == "test"

    def test_pyjwt_expired_fallback(self, monkeypatch):
        """ExpiredSignatureError returns None, no fallback."""
        import ahy_governance.auth as auth_mod
        class FakePyjwt:
            class ExpiredSignatureError(Exception):
                pass
            class InvalidTokenError(Exception):
                pass
            @staticmethod
            def decode(token, secret, algorithms):
                raise FakePyjwt.ExpiredSignatureError("expired")
        monkeypatch.setattr(auth_mod, "_HAS_PYJWT", True)
        monkeypatch.setattr(auth_mod, "_pyjwt", FakePyjwt)
        assert _verify_jwt("some.token.here") is None

    def test_invalid_token_string(self):
        assert _verify_jwt("not-a-jwt") is None
        assert _verify_jwt("") is None

    def test_handrolled_token_no_pyjwt(self, monkeypatch):
        """Hand-rolled JWT works when PyJWT is not installed."""
        import ahy_governance.auth as auth_mod
        monkeypatch.setattr(auth_mod, "_HAS_PYJWT", False)
        payload = {"sub": "u1", "exp": int(time.time()) + 3600}
        token = _make_jwt(payload)
        decoded = _verify_jwt(token)
        assert decoded["sub"] == "u1"


# ── Transparent upgrade ─────────────────────────────────────

class TestTransparentUpgrade:
    def test_legacy_hash_upgraded_on_login(self, auth):
        """SHA-256 passwords should be upgraded to bcrypt on login."""
        # Insert a legacy SHA-256 hash directly
        salt = secrets.token_hex(16)
        pw_hash = hashlib.sha256(f"{salt}:oldpass".encode()).hexdigest()
        stored = f"{salt}:{pw_hash}"

        with sqlite3.connect(auth.db_path) as conn:
            conn.execute(
                "INSERT INTO users (id, email, password_hash, created_at) VALUES (?,?,?,?)",
                ("legacy1", "legacy@test.com", stored, "2026-01-01"),
            )
            conn.commit()

        # Login should succeed
        result = auth.login("legacy@test.com", "oldpass")
        assert result["email"] == "legacy@test.com"

        # Verify the hash was upgraded (if bcrypt available)
        try:
            import bcrypt
            with sqlite3.connect(auth.db_path) as conn:
                row = conn.execute(
                    "SELECT password_hash FROM users WHERE id='legacy1'"
                ).fetchone()
            assert row[0].startswith("$2b$") or row[0].startswith("$2a$")
        except ImportError:
            pass  # bcrypt not installed, upgrade skipped


# ── Singleton ───────────────────────────────────────────────

class TestGetAuth:
    def test_singleton_returns_same(self, tmp_path, monkeypatch):
        import ahy_governance.auth as auth_mod
        auth_mod._auth_instance = None
        db = str(tmp_path / "singleton.db")
        monkeypatch.setenv("AUTH_DB_PATH", db)
        a = get_auth()
        b = get_auth()
        assert a is b
        auth_mod._auth_instance = None

    def test_singleton_from_env(self, tmp_path, monkeypatch):
        import ahy_governance.auth as auth_mod
        auth_mod._auth_instance = None
        db = str(tmp_path / "env.db")
        monkeypatch.setenv("AUTH_DB_PATH", db)
        a = get_auth()
        assert a.db_path == db
        auth_mod._auth_instance = None

    def test_singleton_default_path(self, monkeypatch):
        import ahy_governance.auth as auth_mod
        auth_mod._auth_instance = None
        monkeypatch.delenv("AUTH_DB_PATH", raising=False)
        a = get_auth()
        assert a.db_path == "auth.db"
        auth_mod._auth_instance = None
