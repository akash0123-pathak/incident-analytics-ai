"""Small local-session role gate for the operations workspace.

PIN values are deployment secrets in environment variables. Sessions are stored in SQLite, expire after eight hours, and are checked by
the API—not trusted from the browser's selected role alone.
"""
import os
import secrets
import hashlib
import sqlite3
import time
from pathlib import Path

from fastapi import HTTPException, Request

ROLE_PIN_ENV = {
    "engineer": "ROLE_ENGINEER_PIN",
    "manager": "ROLE_MANAGER_PIN",
    "executive": "ROLE_EXECUTIVE_PIN",
}
_TTL_SECONDS = 8 * 60 * 60
_DB_PATH = Path(os.getenv("APP_DATA_DIR", str(Path(__file__).resolve().parent / "warehouse"))) / "users.sqlite3"


def _connection() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(_DB_PATH)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            expires_at REAL NOT NULL
        )
    """)
    connection.commit()
    return connection


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return f"{salt.hex()}${digest.hex()}"


def _password_matches(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 600_000)
        return secrets.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _create_session(role: str) -> dict:
    token = secrets.token_urlsafe(32)
    with _connection() as connection:
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (time.time(),))
        connection.execute("INSERT INTO sessions (token_hash, role, expires_at) VALUES (?, ?, ?)",
                           (hashlib.sha256(token.encode()).hexdigest(), role, time.time() + _TTL_SECONDS))
    return {"token": token, "role": role, "expires_in": _TTL_SECONDS}


def register(email: str, password: str) -> dict:
    try:
        with _connection() as connection:
            connection.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (email, _hash_password(password)))
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from exc
    return _create_session("engineer")


def account_login(email: str, password: str) -> dict:
    with _connection() as connection:
        row = connection.execute("SELECT password_hash FROM users WHERE email = ?", (email,)).fetchone()
    if not row or not _password_matches(password, row[0]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return _create_session("engineer")


def login(role: str, pin: str) -> dict:
    # IT Support is the local default workspace. Elevated Manager and
    # Executive views remain PIN-gated at the API boundary.
    if role == "engineer":
        return _create_session(role)
    expected = os.getenv(ROLE_PIN_ENV.get(role, ""), "")
    if not expected or not secrets.compare_digest(pin, expected):
        raise HTTPException(status_code=401, detail="Invalid role or PIN.")
    return _create_session(role)


def require_role(request: Request, requested_role: str | None = None) -> str:
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Sign in required.")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with _connection() as connection:
        session = connection.execute("SELECT role, expires_at FROM sessions WHERE token_hash = ?", (token_hash,)).fetchone()
        if session and session[1] <= time.time():
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
    if not session or session[1] <= time.time():
        raise HTTPException(status_code=401, detail="Your session has expired. Sign in again.")
    role = session[0]
    if requested_role and requested_role != role:
        raise HTTPException(status_code=403, detail="This workspace is restricted to your signed-in role.")
    return role
