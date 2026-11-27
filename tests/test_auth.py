import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ.setdefault("VISION_ENABLED", "false")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from backend.app.api import auth  # noqa: E402
from backend.app.core.database import SessionLocal  # noqa: E402
from backend.app.core.security import hash_password, new_totp_secret, totp_now, verify_password, verify_totp  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.models import db  # noqa: E402

pytestmark = pytest.mark.auth


def _make_user(username: str, password: str, email: str | None = None, totp: str | None = None) -> None:
    with SessionLocal() as s:
        if s.scalar(select(db.User).where(db.User.username == username)):
            return
        s.add(db.User(username=username, email=email, role="operator", password_hash=hash_password(password),
                      totp_secret=totp, created_at=0.0))
        s.commit()


def test_password_and_totp_primitives():
    h = hash_password("correct horse")
    assert verify_password("correct horse", h) and not verify_password("wrong", h)
    secret = new_totp_secret()
    assert verify_totp(secret, totp_now(secret)) and not verify_totp(secret, "000000" if totp_now(secret) != "000000" else "111111")


def test_protected_until_login_then_logout():
    with TestClient(app) as c:
        _make_user("op1", "s3cret-pass", email="op1@example.org")
        assert c.get("/api/health").status_code == 200  # stays public
        assert c.get("/api/cameras").status_code == 401
        assert c.get("/api/auth/me").status_code == 401
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect("/ws/live") as ws:
                ws.receive_json()

        bad = c.post("/api/auth/login", json={"username": "op1", "password": "nope"})
        assert bad.status_code == 401 and "sts_session" not in bad.cookies

        ok = c.post("/api/auth/login", json={"username": "OP1@example.org", "password": "s3cret-pass", "remember": True})
        assert ok.status_code == 200 and ok.json()["user"]["username"] == "op1"
        cookie = ok.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie and "max-age" in cookie
        assert c.get("/api/auth/me").json()["username"] == "op1"
        assert c.get("/api/cameras").status_code == 200
        with c.websocket_connect("/ws/live") as ws:
            assert ws.receive_json()["type"] == "snapshot"

        c.post("/api/auth/logout")
        assert c.get("/api/cameras").status_code == 401


def test_session_cookie_without_remember():
    with TestClient(app) as c:
        _make_user("op2", "another-pass")
        r = c.post("/api/auth/login", json={"username": "op2", "password": "another-pass", "remember": False})
        assert r.status_code == 200 and "max-age" not in r.headers["set-cookie"].lower()


def test_two_factor():
    secret = new_totp_secret()
    with TestClient(app) as c:
        _make_user("op3", "mfa-pass-123", totp=secret)
        step1 = c.post("/api/auth/login", json={"username": "op3", "password": "mfa-pass-123"})
        assert step1.json() == {"mfa_required": True} and "sts_session" not in step1.cookies
        assert c.get("/api/auth/me").status_code == 401
        wrong = c.post("/api/auth/login", json={"username": "op3", "password": "mfa-pass-123", "otp": "12345x"})
        assert wrong.status_code == 401
        ok = c.post("/api/auth/login", json={"username": "op3", "password": "mfa-pass-123", "otp": totp_now(secret)})
        assert ok.status_code == 200 and ok.json()["user"]["mfa_enabled"]


def test_lockout_after_repeated_failures():
    with TestClient(app) as c:
        _make_user("op4", "locked-pass")
        for _ in range(auth.MAX_FAILURES):
            assert c.post("/api/auth/login", json={"username": "op4", "password": "x"}).status_code == 401
        r = c.post("/api/auth/login", json={"username": "op4", "password": "locked-pass"})
        assert r.status_code == 429
        auth._clear_failures("op4")


def test_first_start_creates_admin():
    with TestClient(app):
        with SessionLocal() as s:
            admin = s.scalar(select(db.User).where(db.User.role == "admin"))
            assert admin is not None
