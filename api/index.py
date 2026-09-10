"""Vercel entrypoint. Vercel's Python runtime looks for an ASGI application
called `app` in this module and serves it for every route matched in vercel.json."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

__all__ = ["app"]
