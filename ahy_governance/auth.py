"""
Auth module — email/password registration, JWT tokens, API key management.

Zero external dependencies. SQLite for persistence, hand-rolled JWT (HMAC-SHA256).

Usage:
    from ahy_governance.auth import AuthManager
    auth = AuthManager("auth.db")
    user = auth.register("a@b.com", "mypassword")
    token = auth.login("a@b.com", "mypassword")
    key = auth.create_api_key(user["id"], "prod")
"""

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from collections import defaultdict
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


# ── JWT Secret ────────────────────────────────────────────────────

def _load_or_create_jwt_secret() -> str:
    env_secret = os.environ.get("JWT_SECRET")
    if env_secret:
        return env_secret
    secret_file = Path(os.environ.get(
        "AHY_SECRET_DIR",
        Path(__file__).resolve().parent / ".secrets"
    )) / "jwt_secret"
    if secret_file.exists():
        return secret_file.read_text().strip()
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    new_secret = secrets.token_hex(32)
    secret_file.write_text(new_secret)
    return new_secret


# ── Constants ─────────────────────────────────────────────────────

JWT_SECRET = _load_or_create_jwt_secret()
JWT_EXPIRY = 7 * 24 * 3600  # 7 days
API_KEY_PREFIX = "ahy_"


# ── Helpers ────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    iterations = 100_000
    h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), iterations).hex()
    return f"pbkdf2:{salt}:{iterations}:{h}"


def _verify_password(password: str, stored: str) -> bool:
    if stored.startswith("pbkdf2:"):
        _, salt, iterations, h = stored.split(":", 3)
        computed = hashlib.pbkdf2_hmac(
            'sha256', password.encode(), salt.encode(), int(iterations)
        ).hex()
        return hmac.compare_digest(computed, h)
    # Legacy SHA-256 format — verify and auto-upgrade
    salt, h = stored.split(":", 1)
    expected = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return hmac.compare_digest(expected, h)


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── API Key Rate Limiter ───────────────────────────────────────────

# In-memory sliding-window rate limit: 5 failed attempts per 60s per key hash
_rate_limit_store: dict[str, list[float]] = defaultdict(list)


def _check_api_key_rate_limit(key_hash: str, max_attempts: int = 5, window: int = 60) -> bool:
    """Return True if the attempt is allowed, False if rate-limited."""
    now = time.time()
    attempts = _rate_limit_store[key_hash]
    _rate_limit_store[key_hash] = [t for t in attempts if now - t < window]
    if len(_rate_limit_store[key_hash]) >= max_attempts:
        return False
    _rate_limit_store[key_hash].append(now)
    return True


# ── JWT (hand-rolled, no external deps) ───────────────────────────

import base64 as _base64

def _b64(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode()

def _b64_decode(s: str) -> bytes:
    return _base64.urlsafe_b64decode(s + "=" * (4 - len(s) % 4))

def _make_jwt(payload: dict) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64(json.dumps(payload).encode())
    signature = _b64(hmac.new(JWT_SECRET.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest())
    return f"{header}.{body}.{signature}"


def _verify_jwt(token: str) -> dict | None:
    try:
        header, body, signature = token.split(".")
        expected = _b64(hmac.new(JWT_SECRET.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(_b64_decode(body))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


# ── Auth Manager ───────────────────────────────────────────────────

class AuthManager:
    def __init__(self, db_path: str = "auth.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    key_hash TEXT UNIQUE NOT NULL,
                    key_prefix TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            conn.commit()

    # ── User management ────────────────────────────────────────

    def register(self, email: str, password: str) -> dict:
        email = email.strip().lower()
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters")
        user_id = secrets.token_hex(16)
        now = _utc_now()
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    "INSERT INTO users (id, email, password_hash, created_at) VALUES (?,?,?,?)",
                    (user_id, email, _hash_password(password), now),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError("Email already registered")
        return {"id": user_id, "email": email, "created_at": now}

    def login(self, email: str, password: str) -> dict:
        email = email.strip().lower()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, email, password_hash FROM users WHERE email = ?",
                (email,),
            ).fetchone()
        if not row or not _verify_password(password, row[2]):
            raise ValueError("Invalid email or password")
        token = _make_jwt({
            "sub": row[0],
            "email": row[1],
            "exp": int(time.time()) + JWT_EXPIRY,
        })
        return {"user_id": row[0], "email": row[1], "token": token}

    # ── API Keys ───────────────────────────────────────────────

    def create_api_key(self, user_id: str, name: str = "") -> dict:
        raw = API_KEY_PREFIX + secrets.token_hex(24)  # ahy_ + 48 hex chars
        key_id = secrets.token_hex(8)
        now = _utc_now()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO api_keys (id, user_id, key_hash, key_prefix, name, created_at) VALUES (?,?,?,?,?,?)",
                (key_id, user_id, _hash_key(raw), raw[:10], name, now),
            )
            conn.commit()
        return {
            "id": key_id,
            "raw_key": raw,
            "prefix": raw[:10],
            "name": name,
            "created_at": now,
        }

    def list_api_keys(self, user_id: str) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, key_prefix, name, created_at, last_used_at FROM api_keys WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return [{
            "id": r[0], "prefix": r[1], "name": r[2],
            "created_at": r[3], "last_used_at": r[4],
        } for r in rows]

    def delete_api_key(self, user_id: str, key_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "DELETE FROM api_keys WHERE id = ? AND user_id = ?",
                (key_id, user_id),
            )
            conn.commit()
            return cur.rowcount > 0

    # ── Token / Key verification ───────────────────────────────

    def verify_token(self, token: str) -> str | None:
        """Return user_id if token is valid."""
        payload = _verify_jwt(token)
        return payload["sub"] if payload else None

    def verify_api_key(self, raw_key: str) -> str | None:
        """Return user_id if API key is valid, update last_used_at."""
        kh = _hash_key(raw_key)
        if not _check_api_key_rate_limit(kh):
            return None
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT user_id FROM api_keys WHERE key_hash = ?",
                (kh,),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE api_keys SET last_used_at = ? WHERE key_hash = ?",
                    (_utc_now(), kh),
                )
                conn.commit()
                return row[0]
        return None


# ── Global singleton ──────────────────────────────────────────────

_auth_instance: AuthManager | None = None


def get_auth(db_path: str | None = None) -> AuthManager:
    global _auth_instance
    if db_path is None:
        db_path = os.environ.get("AUTH_DB_PATH", "auth.db")
    if _auth_instance is None:
        _auth_instance = AuthManager(db_path)
    return _auth_instance
