"""Optional passwords, sign-in, sign-out and session revocation."""

from __future__ import annotations

import hashlib
import hmac

from fastapi.testclient import TestClient

from scholariq.api.deps import login_limiter
from scholariq.core.config import Settings
from scholariq.core.security import COOKIE_NAME, hash_password, sign, unsign, verify_password


def profile(client: TestClient, name: str = "Asha") -> dict:  # type: ignore[type-arg]
    r = client.post("/api/profile", json={"display_name": name, "consent": True})
    assert r.status_code == 201
    return r.json()  # type: ignore[no-any-return]


def test_password_hashing() -> None:
    stored = hash_password("correct horse battery")
    assert stored.startswith("scrypt$") and "correct" not in stored
    assert verify_password("correct horse battery", stored)
    assert not verify_password("wrong password!", stored)
    assert not verify_password("anything at all", None)
    assert not verify_password("anything at all", "garbage")


def test_tokens_carry_a_version_and_old_tokens_still_work() -> None:
    assert unsign("k", sign("other key", "abc", 3)) is None
    assert unsign("k", sign("k", "abc", 3)) == ("abc", 3)
    # Cookies issued before versions existed: "<id>.<mac over id>".
    old = "abc." + hmac.new(b"k", b"abc", hashlib.sha256).hexdigest()
    assert unsign("k", old) == ("abc", 0)
    assert unsign("k", "abc.1.deadbeef") is None


def test_set_password_sign_out_and_sign_in(client: TestClient) -> None:
    me = profile(client)
    assert me["has_password"] is False
    # Without a password, signing out would strand the profile.
    assert client.post("/api/profile/logout", json={}).status_code == 409

    r = client.put(
        "/api/profile/credentials",
        json={"email": " Asha@Example.org ", "password": "a long passphrase"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "asha@example.org" and r.json()["has_password"]

    assert client.post("/api/profile/logout", json={}).status_code == 204
    assert client.get("/api/profile").status_code == 401

    bad = client.post(
        "/api/profile/login", json={"email": "asha@example.org", "password": "nope nope nope"}
    )
    assert bad.status_code == 401
    unknown = client.post(
        "/api/profile/login", json={"email": "who@example.org", "password": "a long passphrase"}
    )
    assert unknown.status_code == 401 and unknown.json() == bad.json()
    ok = client.post(
        "/api/profile/login", json={"email": "ASHA@example.org", "password": "a long passphrase"}
    )
    assert ok.status_code == 200 and ok.json()["id"] == me["id"]
    assert client.get("/api/profile").status_code == 200


def test_changing_password_needs_the_current_one_and_signs_out_elsewhere(
    client: TestClient, settings: Settings
) -> None:
    profile(client)
    creds = {"email": "a@example.org", "password": "first passphrase"}
    client.put("/api/profile/credentials", json=creds)
    other_browser = client.cookies.get(COOKIE_NAME)

    r = client.put("/api/profile/credentials", json={**creds, "password": "second passphrase"})
    assert r.status_code == 403
    r = client.put(
        "/api/profile/credentials",
        json={**creds, "password": "second passphrase", "current_password": "first passphrase"},
    )
    assert r.status_code == 200
    assert client.get("/api/profile").status_code == 200  # this browser got a new cookie
    client.cookies.set(COOKIE_NAME, other_browser or "")
    assert client.get("/api/profile").status_code == 401


def test_sign_out_everywhere(client: TestClient) -> None:
    profile(client)
    client.put(
        "/api/profile/credentials", json={"email": "b@example.org", "password": "0123456789"}
    )
    stolen = client.cookies.get(COOKIE_NAME)
    assert client.post("/api/profile/logout", json={"everywhere": True}).status_code == 204
    client.cookies.set(COOKIE_NAME, stolen or "")
    assert client.get("/api/profile").status_code == 401


def test_email_must_be_unique_and_passwords_long(client: TestClient) -> None:
    profile(client)
    client.put(
        "/api/profile/credentials", json={"email": "c@example.org", "password": "0123456789"}
    )
    client.cookies.clear()
    profile(client, "Ben")
    r = client.put(
        "/api/profile/credentials", json={"email": "C@example.org", "password": "0123456789"}
    )
    assert r.status_code == 409
    r = client.put("/api/profile/credentials", json={"email": "d@example.org", "password": "short"})
    assert r.status_code == 422


def test_sign_in_is_rate_limited(client: TestClient) -> None:
    login_limiter._hits.clear()
    body = {"email": "e@example.org", "password": "guess guess"}
    codes = [client.post("/api/profile/login", json=body).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
    login_limiter._hits.clear()


def test_api_responses_carry_security_headers(client: TestClient) -> None:
    r = client.get("/api/health/live")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"
