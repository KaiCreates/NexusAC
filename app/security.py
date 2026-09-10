"""Sessions, API keys, rate limiting and the small HTTP helpers shared by every route."""
from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from . import config, db

# The anti-cheat validates its key with `#token ~= 43` and `^[%w_%-]+$`, so the
# key format is fixed at 43 URL-safe characters. token_urlsafe(32) is exactly that.
API_KEY_BYTES = 32
API_KEY_LENGTH = 43

ROLES = ("owner", "administrator", "moderator", "viewer")
PERMISSIONS: dict[str, tuple[str, ...]] = {
    "owner": ("kick", "ban", "freeze", "screenshot", "unban", "setting", "detector"),
    "administrator": ("kick", "ban", "freeze", "screenshot", "unban", "setting", "detector"),
    "moderator": ("kick", "freeze", "screenshot"),
    "viewer": (),
}


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def require(condition: Any, status: int, message: str) -> None:
    if not condition:
        raise HttpError(status, message)


def now() -> int:
    return int(time.time())


def new_id() -> str:
    return str(uuid.uuid4())


def new_secret() -> str:
    return secrets.token_urlsafe(API_KEY_BYTES)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def reply(body: Any, status: int = 200, headers: dict[str, str] | None = None) -> JSONResponse:
    base = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    base.update(headers or {})
    return JSONResponse(body, status_code=status, headers=base)


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #

def set_session_cookie(response: Response, token: str, clear: bool = False) -> None:
    response.set_cookie(
        config.SESSION_COOKIE,
        "" if clear else token,
        max_age=0 if clear else config.SESSION_TTL,
        path="/",
        httponly=True,
        samesite="lax",
        secure=config.IS_PRODUCTION,
    )


def token_from(request: Request) -> str:
    return request.cookies.get(config.SESSION_COOKIE, "")


def create_session(user_id: str, workspace: str) -> str:
    token = new_secret()
    db.execute(
        "INSERT INTO nx_sessions(hash,user_id,workspace,expires) VALUES(%s,%s,%s,%s)",
        (sha256(token), user_id, workspace, now() + config.SESSION_TTL),
    )
    db.execute("DELETE FROM nx_sessions WHERE expires<=%s", (now(),))
    return token


def session_for(request: Request) -> dict | None:
    token = token_from(request)
    if not token:
        return None
    return db.one(
        """SELECT u.id AS user_id, u.name, u.email, s.workspace, m.role
             FROM nx_sessions s
             JOIN nx_users u ON u.id = s.user_id
             JOIN nx_members m ON m.user_id = u.id AND m.workspace = s.workspace
            WHERE s.hash = %s AND s.expires > %s""",
        (sha256(token), now()),
    )


def authenticated(request: Request) -> dict:
    user = session_for(request)
    require(user, 401, "Please sign in.")
    return user  # type: ignore[return-value]


def origin_check(request: Request) -> None:
    """Reject cross-site form posts. The bridge is exempt: it authenticates with a
    bearer key and never carries a cookie, so it cannot be driven by a browser."""
    origin = request.headers.get("origin")
    if origin is None:
        return  # non-browser client; the session cookie is SameSite=Lax anyway
    # The configured public origin, or the one this request actually arrived on —
    # so http://127.0.0.1:3000 and http://localhost:3000 both work in development.
    # A cross-site attacker's origin is neither.
    allowed = {config.APP_URL, str(request.base_url).rstrip("/")}
    require(origin in allowed, 403, "This request must come from your NexusAC website.")


def rate(key: str, maximum: int, seconds: int = 900) -> None:
    row = db.one(
        """INSERT INTO nx_limits(key,count,expires) VALUES(%s,1,%s)
           ON CONFLICT(key) DO UPDATE SET
             count = CASE WHEN nx_limits.expires <= %s THEN 1 ELSE nx_limits.count + 1 END,
             expires = CASE WHEN nx_limits.expires <= %s THEN EXCLUDED.expires ELSE nx_limits.expires END
           RETURNING count""",
        (sha256(key), now() + seconds, now(), now()),
    )
    require(row and row["count"] <= maximum, 429, "Too many requests. Please wait and try again.")


def audit(user: dict, action: str, detail: str) -> None:
    db.execute(
        "INSERT INTO nx_audit VALUES(%s,%s,%s,%s,%s,%s)",
        (new_id(), user["workspace"], user["name"], action, detail[:400], now()),
    )
