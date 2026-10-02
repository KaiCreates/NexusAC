"""Sign-in without an outside identity provider.

Passwords are hashed with scrypt (Python standard library, no extra dependency)
and stored in nx_users.password_hash. Sessions are unchanged: after a password
checks out, api_routes mints the same opaque session cookie as before.

There is no email service, so there is no self-service password reset. An owner
(or whoever runs the site) sets a password with scripts/set_password.py.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

from . import db
from .security import HttpError, new_id, now

# 16 MiB of memory per hash: fine on a 512 MB host, slow enough for brute force.
_N, _R, _P, _LEN = 2 ** 14, 8, 1, 32


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_LEN)
    return "scrypt$%d$%d$%d$%s$%s" % (_N, _R, _P, base64.b64encode(salt).decode(),
                                       base64.b64encode(digest).decode())


def verify_password(password: str, stored: str | None) -> bool:
    try:
        scheme, n, r, p, salt, digest = (stored or "").split("$")
        if scheme != "scrypt":
            return False
        want = base64.b64decode(digest)
        got = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt),
                             n=int(n), r=int(r), p=int(p), dklen=len(want))
        return hmac.compare_digest(got, want)
    except (ValueError, TypeError):
        return False


# Spend the same time on an unknown email as on a wrong password, so the login
# form cannot be used to find out which emails have accounts.
_DUMMY = hash_password(base64.b64encode(os.urandom(12)).decode())


def sign_in(email: str, password: str) -> dict:
    row = db.one("SELECT id, password_hash FROM nx_users WHERE lower(email)=%s", (email,))
    if not row:
        verify_password(password, _DUMMY)
        raise HttpError(401, "Email or password is incorrect.")
    if not row.get("password_hash"):
        raise HttpError(403, "This account was moved from the old sign-in system and has no password yet. "
                             "Ask the site owner to set one (scripts/set_password.py).")
    if not verify_password(password, row["password_hash"]):
        raise HttpError(401, "Email or password is incorrect.")
    return {"id": str(row["id"])}


def sign_up(cur, email: str, password: str, name: str) -> dict:
    """Create the user row inside the caller's transaction (which also creates
    their workspace), so a half-created account cannot exist."""
    cur.execute("SELECT 1 FROM nx_users WHERE lower(email)=%s", (email,))
    if cur.fetchone():
        raise HttpError(409, "An account already exists for that email. Please sign in.")
    user_id = new_id()
    cur.execute(
        "INSERT INTO nx_users(id, email, name, created, password_hash) VALUES(%s,%s,%s,%s,%s)",
        (user_id, email, name, now(), hash_password(password)),
    )
    return {"id": user_id}


def set_password(email: str, password: str) -> bool:
    return db.execute("UPDATE nx_users SET password_hash=%s WHERE lower(email)=%s",
                      (hash_password(password), email.strip().lower())) > 0
