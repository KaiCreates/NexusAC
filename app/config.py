"""Environment configuration. Every secret is read from the environment only."""
from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Load .env when running locally. Vercel injects real environment variables,
    so this is a no-op there."""
    path = _ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} is not set. Copy .env.example to .env (local) or add it in "
            f"Vercel -> Settings -> Environment Variables (production)."
        )
    return value


SUPABASE_URL = _require("SUPABASE_URL").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = _require("SUPABASE_PUBLISHABLE_KEY")
SUPABASE_SECRET_KEY = _require("SUPABASE_SECRET_KEY")
SUPABASE_JWKS_URL = os.environ.get(
    "SUPABASE_JWKS_URL", f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
)
DATABASE_URL = _require("DATABASE_URL")

# Public origin of this website. Used for the CSRF origin check and for the
# redirect target in confirmation emails.
APP_URL = os.environ.get("APP_URL", "http://localhost:3000").rstrip("/")

# Supabase projects ship with email confirmation ON and a heavily rate-limited
# default mail sender (a handful of messages an hour), which makes sign-up look
# broken. With this false the website creates the account pre-confirmed through
# the Supabase admin API and signs the person straight in. Set it to true once
# you have configured your own SMTP provider in Supabase.
REQUIRE_EMAIL_CONFIRMATION = os.environ.get(
    "REQUIRE_EMAIL_CONFIRMATION", "false"
).lower() in ("1", "true", "yes")

SESSION_COOKIE = "nexus_session"
SESSION_TTL = 7 * 24 * 3600
IS_PRODUCTION = bool(os.environ.get("VERCEL")) or APP_URL.startswith("https://")
