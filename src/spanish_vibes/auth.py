from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Request
from starlette.responses import Response

from .db import _open_connection, now_iso

SESSION_COOKIE_NAME = "sv_session"
CSRF_COOKIE_NAME = "sv_csrf"
PBKDF2_ITERATIONS = 390_000
SESSION_TTL_DAYS = 30
_active_user_id: ContextVar[int] = ContextVar("active_user_id", default=0)


@dataclass(frozen=True, slots=True)
class AuthUser:
    id: int
    email: str


def set_active_user_id(user_id: int) -> None:
    _active_user_id.set(max(0, int(user_id)))


def get_active_user_id() -> int:
    return max(0, int(_active_user_id.get()))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _hash_password(password: str, *, salt: bytes | None = None) -> str:
    safe_salt = salt or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        safe_salt,
        PBKDF2_ITERATIONS,
    )
    salt_b64 = base64.b64encode(safe_salt).decode("ascii")
    hash_b64 = base64.b64encode(derived).decode("ascii")
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt_b64}${hash_b64}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, iter_s, salt_b64, hash_b64 = stored_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iter_s)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(hash_b64.encode("ascii"))
    except (ValueError, TypeError):
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def create_user(email: str, password: str) -> AuthUser | None:
    normalized_email = _normalize_email(email)
    if not normalized_email or len(password) < 8:
        return None

    created_at = now_iso()
    password_hash = _hash_password(password)
    with _open_connection() as connection:
        existing = connection.execute(
            "SELECT id FROM users WHERE email = ?",
            (normalized_email,),
        ).fetchone()
        if existing is not None:
            return None
        cursor = connection.execute(
            """
            INSERT INTO users (email, password_hash, created_at)
            VALUES (?, ?, ?)
            """,
            (normalized_email, password_hash, created_at),
        )
        connection.commit()
        return AuthUser(id=int(cursor.lastrowid), email=normalized_email)


def authenticate_user(email: str, password: str) -> AuthUser | None:
    normalized_email = _normalize_email(email)
    with _open_connection() as connection:
        row = connection.execute(
            "SELECT id, email, password_hash FROM users WHERE email = ?",
            (normalized_email,),
        ).fetchone()
        if row is None:
            return None
        if not _verify_password(password, str(row["password_hash"])):
            return None
        connection.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?",
            (now_iso(), int(row["id"])),
        )
        connection.commit()
        return AuthUser(id=int(row["id"]), email=str(row["email"]))


def create_user_session(user_id: int, *, ttl_days: int = SESSION_TTL_DAYS) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = _hash_session_token(token)
    now = _utc_now()
    expires_at = now + timedelta(days=ttl_days)
    timestamp = now_iso(now)
    with _open_connection() as connection:
        connection.execute(
            """
            INSERT INTO user_sessions (user_id, session_token_hash, expires_at, created_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, token_hash, now_iso(expires_at), timestamp, timestamp),
        )
        connection.commit()
    return token


def get_user_by_session_token(token: str | None) -> AuthUser | None:
    if not token:
        return None
    now = _utc_now()
    with _open_connection() as connection:
        row = connection.execute(
            """
            SELECT u.id AS user_id, u.email AS email, s.id AS session_id, s.expires_at AS expires_at
            FROM user_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.session_token_hash = ?
            """,
            (_hash_session_token(token),),
        ).fetchone()
        if row is None:
            return None
        expires_at = datetime.fromisoformat(str(row["expires_at"]))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            connection.execute(
                "DELETE FROM user_sessions WHERE id = ?", (int(row["session_id"]),)
            )
            connection.commit()
            return None
        connection.execute(
            "UPDATE user_sessions SET last_seen_at = ? WHERE id = ?",
            (now_iso(now), int(row["session_id"])),
        )
        connection.commit()
        return AuthUser(id=int(row["user_id"]), email=str(row["email"]))


def revoke_session(token: str | None) -> None:
    if not token:
        return
    with _open_connection() as connection:
        connection.execute(
            "DELETE FROM user_sessions WHERE session_token_hash = ?",
            (_hash_session_token(token),),
        )
        connection.commit()


def cleanup_expired_sessions() -> None:
    with _open_connection() as connection:
        connection.execute(
            "DELETE FROM user_sessions WHERE expires_at <= ?",
            (now_iso(),),
        )
        connection.commit()


def get_current_user(request: Request) -> AuthUser | None:
    user = getattr(request.state, "current_user", None)
    if isinstance(user, AuthUser):
        return user
    return None


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def ensure_csrf_cookie(request: Request, response: Response) -> str:
    token = (
        getattr(request.state, "csrf_token", None)
        or request.cookies.get(CSRF_COOKIE_NAME)
        or generate_csrf_token()
    )
    if request.cookies.get(CSRF_COOKIE_NAME) != token:
        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=token,
            httponly=True,
            secure=(request.url.scheme == "https"),
            samesite="lax",
            max_age=60 * 60 * 24 * 90,
            path="/",
        )
    return token


def validate_csrf(request: Request, form_token: str) -> bool:
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    if not cookie_token or not form_token:
        return False
    return hmac.compare_digest(cookie_token, form_token)


def set_session_cookie(request: Request, response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=(request.url.scheme == "https"),
        samesite="lax",
        max_age=60 * 60 * 24 * SESSION_TTL_DAYS,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
