"""Login / logout / current user, and the guard that protects every other endpoint.

Sessions are server-side rows referenced by an HttpOnly, SameSite=Lax cookie, so the
browser sends them automatically to REST calls, camera <img> streams and the WebSocket,
and page JavaScript can never read the token.
"""
from __future__ import annotations

import logging
import secrets
import threading
import time
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response, WebSocketException, status
from fastapi.requests import HTTPConnection
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select

from backend.app.core.config import ROOT, settings
from backend.app.core.database import SessionLocal
from backend.app.core.security import (
    DUMMY_HASH,
    hash_password,
    new_session_token,
    token_digest,
    verify_password,
    verify_totp,
)
from backend.app.models import db

log = logging.getLogger("auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE = "sts_session"
PUBLIC_PATHS = {"/api/health"}  # liveness check stays open for monitoring

# ---------------------------------------------------------------- brute-force protection
MAX_FAILURES, WINDOW_S, LOCK_S = 5, 15 * 60, 15 * 60
_failures: dict[str, list[float]] = defaultdict(list)
_lock = threading.Lock()


def _locked_for(key: str) -> float:
    now = time.time()
    with _lock:
        recent = [t for t in _failures[key] if now - t < WINDOW_S]
        _failures[key] = recent
        if len(recent) >= MAX_FAILURES:
            return max(0.0, recent[-1] + LOCK_S - now)
    return 0.0


def _record_failure(key: str) -> None:
    with _lock:
        _failures[key].append(time.time())


def _clear_failures(key: str) -> None:
    with _lock:
        _failures.pop(key, None)


# ---------------------------------------------------------------- helpers
def public_user(u: db.User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "display_name": u.display_name or u.username,
        "role": u.role,
        "mfa_enabled": bool(u.totp_secret),
        "last_login": u.last_login,
    }


def _user_from_token(token: str | None) -> db.User | None:
    if not token:
        return None
    with SessionLocal() as s:
        row = s.get(db.UserSession, token_digest(token))
        if not row:
            return None
        if row.expires_at < time.time():
            s.delete(row)
            s.commit()
            return None
        user = s.get(db.User, row.user_id)
        return user if user and user.is_active else None


def require_user(conn: HTTPConnection) -> db.User | None:
    """Dependency for every protected route and the WebSocket."""
    if conn.url.path in PUBLIC_PATHS:
        return None
    user = _user_from_token(conn.cookies.get(COOKIE))
    if user is None:
        if conn.scope["type"] == "websocket":
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Not signed in")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    return user


def ensure_admin() -> None:
    """Create the first admin account if there are no users yet."""
    with SessionLocal() as s:
        if s.scalar(select(func.count()).select_from(db.User)):
            return
        password = settings.admin_password
        generated = password is None
        if generated:
            password = secrets.token_urlsafe(12)
        s.add(db.User(username=settings.admin_username, email=settings.admin_email, display_name="Administrator",
                      role="admin", password_hash=hash_password(password), created_at=time.time()))
        s.commit()
    if generated:
        if settings.database_url.startswith("sqlite:///"):
            out_dir = Path(settings.database_url.removeprefix("sqlite:///")).parent
        else:
            out_dir = ROOT / "data"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "admin-credentials.txt"
        path.write_text(
            f"Smart Traffic System - first administrator account\n\nUsername: {settings.admin_username}\n"
            f"Password: {password}\n\nChange it with:  python scripts/manage_users.py passwd {settings.admin_username}\n"
            "then delete this file.\n",
            encoding="utf-8",
        )
        log.warning("Created admin account '%s' with a generated password; see %s", settings.admin_username, path)
    else:
        log.info("Created admin account '%s' from ADMIN_PASSWORD", settings.admin_username)


# ---------------------------------------------------------------- endpoints
class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=254, description="Username or email")
    password: str = Field(min_length=1, max_length=1024)
    remember: bool = False
    otp: str | None = Field(None, max_length=16, description="6-digit code when 2FA is enabled")


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response) -> dict:
    ident = body.username.strip()
    key = ident.lower()
    wait = _locked_for(key)
    if wait:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Too many failed attempts. Try again in {int(wait // 60) + 1} minute(s).")

    with SessionLocal() as s:
        user = s.scalar(select(db.User).where(or_(func.lower(db.User.username) == key, func.lower(db.User.email) == key)))
        ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
        if not user or not ok or not user.is_active:
            _record_failure(key)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password.")

        if user.totp_secret:
            if not body.otp:
                return {"mfa_required": True}
            if not verify_totp(user.totp_secret, body.otp):
                _record_failure(key)
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication code.")

        _clear_failures(key)
        now = time.time()
        lifetime = settings.remember_days * 86400 if body.remember else settings.session_hours * 3600
        token = new_session_token()
        s.execute(delete(db.UserSession).where(db.UserSession.expires_at < now))  # housekeeping
        s.add(db.UserSession(id=token_digest(token), user_id=user.id, created_at=now, expires_at=now + lifetime,
                             user_agent=(request.headers.get("user-agent") or "")[:255],
                             ip=request.client.host if request.client else None))
        user.last_login = now
        s.add(db.SystemEvent(ts=now, level="info", component="auth", message=f"User '{user.username}' signed in"))
        s.commit()
        result = {"mfa_required": False, "user": public_user(user)}

    response.set_cookie(
        COOKIE, token,
        max_age=int(lifetime) if body.remember else None,  # no max_age = ends when the browser closes
        httponly=True, samesite="lax", secure=settings.cookie_secure, path="/",
    )
    return result


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(COOKIE)
    if token:
        with SessionLocal() as s:
            s.execute(delete(db.UserSession).where(db.UserSession.id == token_digest(token)))
            s.commit()
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="lax", secure=settings.cookie_secure)
    return {"ok": True}


@router.get("/me")
def me(request: Request) -> dict:
    user = _user_from_token(request.cookies.get(COOKIE))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    return public_user(user)
