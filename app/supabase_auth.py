"""Supabase Auth is the identity provider: it stores passwords, hashes them and
owns email confirmation and password resets.

The website does not keep Supabase's access token around after sign-in. It reads
the user id out of the freshly issued JWT (verified against the project's JWKS)
and then mints its own opaque session cookie, so rendering a page never depends
on refreshing a Supabase token.
"""
from __future__ import annotations

import threading
import time
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from . import config
from .security import HttpError, require

_AUTH = f"{config.SUPABASE_URL}/auth/v1"
_TIMEOUT = httpx.Timeout(15.0, connect=10.0)

_jwk_lock = threading.Lock()
_jwk_client: PyJWKClient | None = None


def _client() -> httpx.Client:
    return httpx.Client(timeout=_TIMEOUT)


def _anon_headers() -> dict[str, str]:
    return {
        "apikey": config.SUPABASE_PUBLISHABLE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_PUBLISHABLE_KEY}",
        "Content-Type": "application/json",
    }


def _admin_headers() -> dict[str, str]:
    return {
        "apikey": config.SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {config.SUPABASE_SECRET_KEY}",
        "Content-Type": "application/json",
    }


def _message(response: httpx.Response, fallback: str) -> str:
    try:
        body = response.json()
    except Exception:
        return fallback
    for key in ("msg", "message", "error_description", "error"):
        value = body.get(key) if isinstance(body, dict) else None
        if isinstance(value, str) and value:
            return value
    return fallback


def _jwks() -> PyJWKClient:
    global _jwk_client
    with _jwk_lock:
        if _jwk_client is None:
            _jwk_client = PyJWKClient(config.SUPABASE_JWKS_URL, cache_keys=True, lifespan=3600)
        return _jwk_client


def identity_from_token(access_token: str) -> dict[str, Any]:
    """Return {id, email} for a Supabase access token.

    Verified locally against the project JWKS (asymmetric signing keys). Projects
    still on a legacy shared HS256 secret publish no usable JWKS, so that case
    falls back to asking Supabase who the token belongs to.
    """
    try:
        key = _jwks().get_signing_key_from_jwt(access_token).key
        claims = jwt.decode(
            access_token,
            key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            issuer=f"{_AUTH}",
            options={"require": ["sub", "exp"]},
        )
        return {"id": claims["sub"], "email": (claims.get("email") or "").lower()}
    except Exception:
        with _client() as http:
            response = http.get(
                f"{_AUTH}/user",
                headers={
                    "apikey": config.SUPABASE_PUBLISHABLE_KEY,
                    "Authorization": f"Bearer {access_token}",
                },
            )
        require(response.status_code == 200, 401, "Could not verify your sign-in with Supabase.")
        body = response.json()
        return {"id": body["id"], "email": (body.get("email") or "").lower()}


def sign_in(email: str, password: str) -> dict[str, Any]:
    """Exchange an email and password for an identity. Raises 401 on bad credentials."""
    with _client() as http:
        response = http.post(
            f"{_AUTH}/token",
            params={"grant_type": "password"},
            headers=_anon_headers(),
            json={"email": email, "password": password},
        )
    if response.status_code != 200:
        message = _message(response, "Email or password is incorrect.")
        if "not confirmed" in message.lower():
            raise HttpError(403, "Confirm your email address before signing in.")
        raise HttpError(401, "Email or password is incorrect.")
    body = response.json()
    token = body.get("access_token")
    require(token, 401, "Supabase did not return a session.")
    return identity_from_token(token)


def sign_up(email: str, password: str, name: str) -> dict[str, Any]:
    """Create an account.

    Returns {"identity": {...}} when the person can be signed in immediately, or
    {"confirm": True} when Supabase has sent a confirmation email instead.
    """
    if config.REQUIRE_EMAIL_CONFIRMATION:
        with _client() as http:
            response = http.post(
                f"{_AUTH}/signup",
                headers=_anon_headers(),
                json={
                    "email": email,
                    "password": password,
                    "data": {"name": name},
                    "options": {"email_redirect_to": f"{config.APP_URL}/login"},
                },
            )
        if response.status_code not in (200, 201):
            raise HttpError(400, _message(response, "Could not create that account."))
        body = response.json()
        if body.get("access_token"):
            return {"identity": identity_from_token(body["access_token"])}
        return {"confirm": True}

    # Confirmation disabled: create the account already confirmed through the admin
    # API, then sign in normally. Supabase's built-in mailer is rate limited to a
    # few messages an hour, which would otherwise make sign-up look broken.
    with _client() as http:
        response = http.post(
            f"{_AUTH}/admin/users",
            headers=_admin_headers(),
            json={
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"name": name},
            },
        )
    if response.status_code not in (200, 201):
        message = _message(response, "Could not create that account.")
        if response.status_code in (409, 422) or "already" in message.lower():
            raise HttpError(409, "An account already exists for that email. Please sign in.")
        raise HttpError(400, message)
    return {"identity": sign_in(email, password)}


def send_password_reset(email: str) -> None:
    with _client() as http:
        http.post(
            f"{_AUTH}/recover",
            headers=_anon_headers(),
            json={"email": email},
            params={"redirect_to": f"{config.APP_URL}/login"},
        )
