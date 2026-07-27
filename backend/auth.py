"""Simple username/password authentication.

Users live in data/users.json (pbkdf2-sha256 salted hashes). Login returns an
HMAC-signed, expiring token that the frontend sends as `Authorization: Bearer`.
The signing secret is kept in data/.auth_secret so tokens survive restarts.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional

from . import config

USERS_FILE = config.DATA_DIR / "users.json"
SECRET_FILE = config.DATA_DIR / ".auth_secret"
TOKEN_TTL = 12 * 3600  # 12 hours

DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "admin123"


def _secret() -> bytes:
    if not SECRET_FILE.exists():
        SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        SECRET_FILE.write_bytes(secrets.token_bytes(32))
    return SECRET_FILE.read_bytes()


def _hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000).hex()


def load_users() -> dict:
    if not USERS_FILE.exists():
        return {}
    try:
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(users: dict) -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(users, indent=2), encoding="utf-8")


def create_user(username: str, password: str) -> None:
    users = load_users()
    salt = secrets.token_bytes(16)
    users[username] = {"salt": salt.hex(), "hash": _hash(password, salt)}
    _save(users)


def set_password(username: str, password: str) -> bool:
    if username not in load_users():
        return False
    create_user(username, password)
    return True


def verify(username: str, password: str) -> bool:
    rec = load_users().get(username)
    if not rec:
        return False
    return hmac.compare_digest(_hash(password, bytes.fromhex(rec["salt"])), rec["hash"])


def ensure_seed_user() -> Optional[tuple]:
    """Create the default admin on first run. Returns (user, pw) if created."""
    if load_users():
        return None
    create_user(DEFAULT_USER, DEFAULT_PASSWORD)
    return (DEFAULT_USER, DEFAULT_PASSWORD)


def make_token(username: str, ttl: int = TOKEN_TTL) -> str:
    exp = int(time.time()) + ttl
    msg = f"{username}|{exp}"
    sig = hmac.new(_secret(), msg.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{msg}|{sig}".encode()).decode()


def check_token(token: str) -> Optional[str]:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        username, exp, sig = raw.split("|")
        if int(exp) < time.time():
            return None
        good = hmac.new(_secret(), f"{username}|{exp}".encode(), hashlib.sha256).hexdigest()
        return username if hmac.compare_digest(good, sig) else None
    except Exception:
        return None
