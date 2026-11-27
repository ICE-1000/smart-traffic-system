"""Manage dashboard login accounts.

Run from the project folder with the virtual environment active:

    python scripts/manage_users.py list
    python scripts/manage_users.py add  <username> [--email E] [--name N] [--admin]
    python scripts/manage_users.py passwd <username>          # set a new password
    python scripts/manage_users.py enable-2fa  <username>     # prints the authenticator setup key
    python scripts/manage_users.py disable-2fa <username>
    python scripts/manage_users.py disable <username> | enable <username> | delete <username>

Passwords are typed at a hidden prompt (or passed with --password for automation).
"""
from __future__ import annotations

import argparse
import getpass
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select  # noqa: E402

from backend.app.core.database import SessionLocal, run_migrations  # noqa: E402
from backend.app.core.security import hash_password, new_totp_secret, totp_uri  # noqa: E402
from backend.app.models import db  # noqa: E402


def ask_password(given: str | None) -> str:
    if given:
        pw = given
    else:
        pw = getpass.getpass("New password: ")
        if pw != getpass.getpass("Repeat password: "):
            sys.exit("Passwords do not match.")
    if len(pw) < 8:
        sys.exit("Use at least 8 characters.")
    return pw


def find(s, username: str) -> db.User:
    u = s.scalar(select(db.User).where(func.lower(db.User.username) == username.lower()))
    if not u:
        sys.exit(f"No user '{username}'.")
    return u


def end_sessions(s, u: db.User) -> None:
    s.execute(delete(db.UserSession).where(db.UserSession.user_id == u.id))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["list", "add", "passwd", "enable-2fa", "disable-2fa", "disable", "enable", "delete"])
    ap.add_argument("username", nargs="?")
    ap.add_argument("--email")
    ap.add_argument("--name")
    ap.add_argument("--admin", action="store_true")
    ap.add_argument("--password")
    a = ap.parse_args()
    if a.command != "list" and not a.username:
        ap.error("username is required")

    run_migrations()
    with SessionLocal() as s:
        if a.command == "list":
            for u in s.scalars(select(db.User).order_by(db.User.username)):
                last = time.strftime("%Y-%m-%d %H:%M", time.localtime(u.last_login)) if u.last_login else "never"
                print(f"{u.username:<20} {u.role:<9} {'active' if u.is_active else 'DISABLED':<9} "
                      f"2FA={'on ' if u.totp_secret else 'off'}  last login: {last}  {u.email or ''}")
            return
        if a.command == "add":
            if s.scalar(select(db.User).where(func.lower(db.User.username) == a.username.lower())):
                sys.exit(f"User '{a.username}' already exists.")
            s.add(db.User(username=a.username, email=a.email, display_name=a.name, role="admin" if a.admin else "operator",
                          password_hash=hash_password(ask_password(a.password)), created_at=time.time()))
            s.commit()
            print(f"Created '{a.username}'.")
            return
        u = find(s, a.username)
        if a.command == "passwd":
            u.password_hash = hash_password(ask_password(a.password))
            end_sessions(s, u)
            print("Password changed; existing sign-ins were ended.")
        elif a.command == "enable-2fa":
            u.totp_secret = new_totp_secret()
            print("Add this account to an authenticator app (Google Authenticator, Microsoft Authenticator, ...):")
            print(f"  Setup key : {u.totp_secret}")
            print(f"  or URI    : {totp_uri(u.totp_secret, u.username)}")
            print("From now on, sign-in asks for the 6-digit code.")
        elif a.command == "disable-2fa":
            u.totp_secret = None
            print("2FA disabled.")
        elif a.command == "disable":
            u.is_active = False
            end_sessions(s, u)
            print("Account disabled.")
        elif a.command == "enable":
            u.is_active = True
            print("Account enabled.")
        elif a.command == "delete":
            end_sessions(s, u)
            s.delete(u)
            print("Account deleted.")
        s.commit()


if __name__ == "__main__":
    main()
