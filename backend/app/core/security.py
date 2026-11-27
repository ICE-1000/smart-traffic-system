"""Password hashing, session tokens and TOTP (RFC 6238) using only the standard library."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time

# scrypt parameters (~16 MB memory, ~50 ms on a laptop): strong enough for an operator console.
_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, maxmem=64 * 1024 * 1024)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(dk_b64)
        dk = hashlib.scrypt(password.encode(), salt=salt, n=int(n), r=int(r), p=int(p),
                            maxmem=64 * 1024 * 1024, dklen=len(expected))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


# Used to spend the same time on unknown usernames as on known ones (no user enumeration by timing).
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    """Only the SHA-256 of a session token is stored, so a leaked database cannot be replayed."""
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------- TOTP (Google Authenticator etc.)
def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _hotp(secret: str, counter: int, digits: int = 6) -> str:
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    code = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 10**digits
    return str(code).zfill(digits)


def totp_now(secret: str, at: float | None = None, step: int = 30) -> str:
    return _hotp(secret, int((at if at is not None else time.time()) // step))


def verify_totp(secret: str, code: str, at: float | None = None, step: int = 30, window: int = 1) -> bool:
    code = "".join(ch for ch in code if ch.isdigit())
    if len(code) != 6:
        return False
    counter = int((at if at is not None else time.time()) // step)
    return any(hmac.compare_digest(_hotp(secret, counter + d), code) for d in range(-window, window + 1))


def totp_uri(secret: str, username: str, issuer: str = "Smart Traffic System") -> str:
    from urllib.parse import quote

    return f"otpauth://totp/{quote(issuer)}:{quote(username)}?secret={secret}&issuer={quote(issuer)}"
