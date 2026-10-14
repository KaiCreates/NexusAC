"""Passwords, signed session cookies, and the roles.

Sessions are stateless: the cookie carries the username, an expiry and the
account's version, signed with HMAC. Checking one costs a hash, not a query.
Changing a password or deleting an account bumps the version, which kills
every cookie issued before.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from . import store

COOKIE = "nx"
SESSION_SECONDS = 7 * 24 * 3600

# The anti-cheat's own roles, most privileged first. The game server turns the
# role into permissions with its own role table (Nx.roleCaps), so permission
# changes made in the panel apply to the website too.
ROLES = ("owner", "head_admin", "admin", "moderator")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$" + salt.hex() + "$" + digest.hex()


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        test = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(test.hex(), digest)
    except (ValueError, TypeError):
        return False


def _sign(raw: bytes) -> str:
    return hmac.new(store.state["secret"].encode(), raw, hashlib.sha256).hexdigest()


def make_cookie(username: str) -> str:
    user = store.state["users"][username]
    raw = json.dumps({"u": username, "e": int(time.time()) + SESSION_SECONDS, "v": user.get("v", 0)}).encode()
    return base64.urlsafe_b64encode(raw).decode() + "." + _sign(raw)


def read_cookie(value: str | None) -> dict | None:
    """The account behind a cookie, or None. Includes its username."""
    if not value or "." not in value:
        return None
    body, sig = value.rsplit(".", 1)
    try:
        raw = base64.urlsafe_b64decode(body.encode())
    except ValueError:
        return None
    if not hmac.compare_digest(_sign(raw), sig):
        return None
    data = json.loads(raw)
    user = store.state["users"].get(data.get("u"))
    if not user or data.get("e", 0) < time.time() or data.get("v") != user.get("v", 0):
        return None
    return {"username": data["u"], **user}


def new_server_key() -> tuple[str, str]:
    """A 43-character key (what FiveM's nexus_web_token holds) and its hash."""
    key = secrets.token_urlsafe(32)
    return key, hashlib.sha256(key.encode()).hexdigest()


def key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()
