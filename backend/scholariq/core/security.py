"""Signed session cookies and password hashing for student profiles.

A browser holds an HttpOnly cookie with the student id, the profile's session
version and an HMAC over both. Raising the session version (on "sign out
everywhere" or a password change) invalidates every cookie issued before.
Cookies from before session versions existed carry no version and count as
version 0.

A password is optional. Setting one (with an email address used only as the
sign-in name) lets the student sign in from another browser and sign out.
Passwords are hashed with scrypt from the standard library.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

COOKIE_NAME = "scholariq_session"
COOKIE_MAX_AGE = 180 * 24 * 3600

# scrypt cost: 2^14 x 8 x 1 uses 16 MiB and takes tens of milliseconds.
_N, _R, _P = 2**14, 8, 1


def _mac(secret: str, value: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def sign(secret: str, student_id: str, version: int = 0) -> str:
    payload = f"{student_id}.{version}"
    return f"{payload}.{_mac(secret, payload)}"


def unsign(secret: str, token: str | None) -> tuple[str, int] | None:
    """(student id, session version) for a valid token, else None."""
    if not token:
        return None
    parts = token.split(".")
    if len(parts) == 3 and parts[1].isdigit():
        payload = f"{parts[0]}.{parts[1]}"
        if hmac.compare_digest(parts[2], _mac(secret, payload)):
            return parts[0], int(parts[1])
        return None
    if len(parts) == 2 and hmac.compare_digest(parts[1], _mac(secret, parts[0])):
        return parts[0], 0  # issued before session versions existed
    return None


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


# Verified against when no account matches, so a wrong email costs the same time.
_DUMMY = hash_password(secrets.token_hex(16))


def verify_password(password: str, stored: str | None) -> bool:
    try:
        _, n, r, p, salt, digest = (stored or _DUMMY).split("$")
        candidate = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32
        )
    except (ValueError, TypeError):
        return False
    return stored is not None and hmac.compare_digest(candidate.hex(), digest)
