"""Signed session cookies for local student profiles.

A profile is identified by an HMAC-signed student id in an HttpOnly cookie.
There are no passwords yet: this is a single-device profile, suitable for a
local or trusted deployment. Account login arrives with multi-user hardening.
"""

from __future__ import annotations

import hashlib
import hmac

COOKIE_NAME = "scholariq_session"
COOKIE_MAX_AGE = 180 * 24 * 3600


def _mac(secret: str, value: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def sign(secret: str, student_id: str) -> str:
    return f"{student_id}.{_mac(secret, student_id)}"


def unsign(secret: str, token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    student_id, mac = token.rsplit(".", 1)
    return student_id if hmac.compare_digest(mac, _mac(secret, student_id)) else None
