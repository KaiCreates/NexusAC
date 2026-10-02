"""Environment configuration. Every secret is read from the environment only."""
from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Load .env when running locally. Hosts inject real environment variables,
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


def _where() -> str:
    """Name the place the operator actually has to go, so a boot failure in a
    hosting log is directly actionable."""
    if os.environ.get("RENDER"):
        return "Render -> your service -> Environment"
    if os.environ.get("VERCEL"):
        return "Vercel -> Settings -> Environment Variables"
    return "your .env file (copy .env.example to .env)"


# Any Postgres works (Neon, Render, self-hosted, Supabase). Sign-in is built in
# (app/local_auth.py), so the database URL is the only thing required.
_REQUIRED = ("DATABASE_URL",)
_missing = [name for name in _REQUIRED if not os.environ.get(name, "").strip()]
if _missing:
    # Report every missing variable at once. Failing on the first one costs a
    # whole redeploy cycle per variable, which on a hosted service is minutes
    # each and reads like the fix did not work.
    raise RuntimeError(
        "NexusAC is not configured. Missing: "
        + ", ".join(_missing)
        + f". Set {'it' if len(_missing) == 1 else 'them'} in "
        + _where()
        + ". APP_URL should also be this site's public URL, or sign-in is "
          "rejected by the origin check (Render supplies it automatically)."
    )


def _require(name: str) -> str:
    return os.environ[name].strip()


DATABASE_URL = _require("DATABASE_URL")

# Optional until the WebRTC signaling rollout is enabled. These credentials are
# server-side only and must never be included in an API response or client bundle.
CLOUDFLARE_REALTIME_APP_ID = os.environ.get("CLOUDFLARE_REALTIME_APP_ID", "").strip()
CLOUDFLARE_REALTIME_APP_SECRET = os.environ.get(
    "CLOUDFLARE_REALTIME_APP_SECRET", ""
).strip()

# Public origin of this website. Used for the CSRF origin check and for the
# redirect target in confirmation emails. Render publishes the service's own URL,
# so falling back to it means a deploy works before anyone sets APP_URL by hand;
# an explicit APP_URL still wins, which is what a custom domain needs.
APP_URL = (
    os.environ.get("APP_URL")
    or os.environ.get("RENDER_EXTERNAL_URL")
    or "http://localhost:3000"
).rstrip("/")

# Kept for the sign-up page template; there is no email confirmation any more.
REQUIRE_EMAIL_CONFIRMATION = False

SESSION_COOKIE = "nexus_session"
SESSION_TTL = 7 * 24 * 3600
IS_PRODUCTION = (
    bool(os.environ.get("VERCEL"))
    or bool(os.environ.get("RENDER"))
    or APP_URL.startswith("https://")
)
