"""NexusAC website.

One FastAPI application serving three things:
  * /api/control/bridge/*  - the anti-cheat's outbound bridge (API key auth)
  * /api/control/*         - the JSON API this site's own pages call (cookie auth)
  * everything else        - the server-rendered pages
"""
from __future__ import annotations

import logging
import traceback
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from . import config
from .api_routes import router as api_router
from .protocol import issues
from .security import HttpError, reply, session_for

log = logging.getLogger("nexusac")
ROOT = Path(__file__).resolve().parent

app = FastAPI(title="NexusAC", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(api_router, prefix="/api/control")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
templates = Jinja2Templates(directory=str(ROOT / "templates"))


def _wants_json(request: Request) -> bool:
    return request.url.path.startswith("/api/") or "application/json" in (
        request.headers.get("accept", "")
    )


@app.exception_handler(HttpError)
async def http_error(request: Request, error: HttpError):
    if _wants_json(request):
        return reply({"error": error.message}, error.status)
    if error.status in (401, 403) and not request.url.path.startswith("/api/"):
        return RedirectResponse("/login?next=" + request.url.path, status_code=303)
    return templates.TemplateResponse(
        request, "error.html", {"status": error.status, "message": error.message},
        status_code=error.status,
    )


@app.exception_handler(ValidationError)
async def validation_error(request: Request, error: ValidationError):
    return reply({"error": "Invalid request.", "details": issues(error)}, 400)


@app.exception_handler(Exception)
async def unhandled(request: Request, error: Exception):
    # Never let a database URL or key reach the browser.
    log.error("[NexusAC] %s\n%s", error, traceback.format_exc())
    message = "Service unavailable. Check the server log and the database configuration."
    if _wants_json(request):
        # The bridge needs a stable diagnostic without exposing SQL, URLs, or
        # stack traces. The class name lets `nexusweb` distinguish a schema,
        # database, and application failure while the real detail stays in the
        # server log.
        if request.url.path.startswith("/api/control/bridge/"):
            return reply({"error": message, "code": type(error).__name__}, 503)
        return reply({"error": message}, 503)
    return templates.TemplateResponse(
        request, "error.html", {"status": 503, "message": message}, status_code=503
    )


@app.get("/health")
async def health():
    from . import db

    try:
        db.ensure_schema()
        database = "ok"
        status = 200
    except Exception as error:  # surfaced deliberately: this endpoint exists to diagnose
        database = "unavailable: " + type(error).__name__
        status = 503
    return JSONResponse(
        {"service": "nexusac-web", "database": database, "schema": "ok" if status == 200 else "error"},
        status_code=status,
    )


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #

def _page(request: Request, name: str, **context) -> HTMLResponse:
    user = None
    try:
        user = session_for(request)
    except Exception:
        pass  # a page must still render when the database is down
    return templates.TemplateResponse(request, name, {"user": user, **context})


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    if session_for(request):
        return RedirectResponse("/dashboard", status_code=303)
    return _page(request, "landing.html")


@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    if session_for(request):
        return RedirectResponse("/dashboard", status_code=303)
    return _page(request, "auth.html", mode="login")


@app.get("/register", response_class=HTMLResponse)
async def register(request: Request):
    if session_for(request):
        return RedirectResponse("/dashboard", status_code=303)
    return _page(request, "auth.html", mode="register",
                 confirm_required=config.REQUIRE_EMAIL_CONFIRMATION)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not session_for(request):
        return RedirectResponse("/login?next=/dashboard", status_code=303)
    return _page(request, "dashboard.html")


@app.get("/dashboard/servers/{server_id}", response_class=HTMLResponse)
async def server_page(request: Request, server_id: str):
    if not session_for(request):
        return RedirectResponse("/login?next=/dashboard", status_code=303)
    return _page(request, "server.html", server_id=server_id)


@app.get("/identities", response_class=HTMLResponse)
async def identities_page(request: Request):
    if not session_for(request):
        return RedirectResponse("/login?next=/identities", status_code=303)
    return _page(request, "identities.html", query=request.query_params.get("q", ""))


@app.get("/events", response_class=HTMLResponse)
async def events_page(request: Request):
    if not session_for(request):
        return RedirectResponse("/login?next=/events", status_code=303)
    return _page(request, "events.html", query=request.query_params.get("q", ""))


@app.get("/punishments", response_class=HTMLResponse)
async def punishments_page(request: Request):
    if not session_for(request):
        return RedirectResponse("/login?next=/punishments", status_code=303)
    return _page(request, "punishments.html", query=request.query_params.get("q", ""))


@app.get("/docs", response_class=HTMLResponse)
async def docs(request: Request):
    return _page(request, "docs.html", app_url=config.APP_URL)


# The interactive demo. Simulated data only, generated in the browser — it never
# touches the database, and needs no account.
DEMO_SECTIONS = (
    "overview", "servers", "players", "detections", "bans", "screenshots",
    "protection", "events", "logs", "staff", "integrations", "license", "settings",
)


@app.get("/demo", response_class=HTMLResponse)
async def demo(request: Request):
    return _page(request, "demo.html", section="overview")


@app.get("/demo/{section}", response_class=HTMLResponse)
async def demo_section(request: Request, section: str):
    if section not in DEMO_SECTIONS:
        raise HttpError(404, "That demo section does not exist.")
    return _page(request, "demo.html", section=section)
