"""NexusAC web panel.

The in-game staff panel (NexusAC/html/panel.*), served on the web. Every page
and button talks to the game server through the live link in hub.py, and the
game server answers with the same code that answers staff in game -- so the
website and the in-game panel can never drift apart.

Run: uvicorn app.main:app   (ONE worker: the live link lives in memory)
"""
import contextlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import auth, hub, store

HERE = Path(__file__).parent
PAGES = HERE / "pages"
PANEL = HERE / "panel"
SECURE_COOKIE = os.environ.get("COOKIE_SECURE", "1") != "0"
MAX_BRIDGE_BODY = 30 * 1024 * 1024
NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


# --------------------------------------------------------------------- helpers
def ok(**data) -> JSONResponse:
    return JSONResponse({"ok": True, **data})


def fail(msg: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "msg": msg}, status_code=status)


def me(request: Request) -> dict | None:
    return auth.read_cookie(request.cookies.get(auth.COOKIE))


async def body_json(request: Request, limit: int = 256 * 1024) -> dict:
    raw = await request.body()
    if len(raw) > limit:
        raise ValueError("too large")
    data = json.loads(raw or b"{}")
    if not isinstance(data, dict):
        raise ValueError("not an object")
    return data


def guarded(owner_only: bool = False):
    """Signed in (and owner, if asked). POSTs also need the X-NX header, which
    a cross-site form or image cannot send: that is the CSRF guard."""
    def wrap(fn):
        async def inner(request: Request):
            if request.method != "GET" and request.headers.get("x-nx") != "1":
                return fail("Bad request.", 403)
            user = me(request)
            if not user:
                return fail("Sign in again.", 401)
            if owner_only and user["role"] != "owner":
                return fail("Only the owner can do that.", 403)
            request.state.user = user
            try:
                return await fn(request)
            except (ValueError, json.JSONDecodeError):
                return fail("Bad request.")
        return inner
    return wrap


class Limiter:
    """Fixed-window counters in memory."""
    def __init__(self) -> None:
        self.hits: dict[str, list] = {}

    def allow(self, key: str, limit: int, window: float) -> bool:
        now = time.monotonic()
        h = self.hits.get(key)
        if not h or now - h[0] >= window:
            self.hits[key] = [now, 1]
            if len(self.hits) > 5000:
                self.hits.clear()
            return True
        h[1] += 1
        return h[1] <= limit


limiter = Limiter()


def set_session(resp: Response, username: str) -> Response:
    resp.set_cookie(auth.COOKIE, auth.make_cookie(username), max_age=auth.SESSION_SECONDS,
                    httponly=True, secure=SECURE_COOKIE, samesite="lax", path="/")
    return resp


# ----------------------------------------------------------------------- pages
async def index(request: Request):
    if not store.state["users"]:
        return FileResponse(PAGES / "setup.html")
    if not me(request):
        return FileResponse(PAGES / "login.html")
    return FileResponse(PAGES / "home.html")


_panel_html: str | None = None


def panel_html() -> str:
    """panel.html from the game, pointed at the web transport."""
    global _panel_html
    if _panel_html is None:
        html = (PANEL / "panel.html").read_text(encoding="utf-8")
        html = html.replace('href="panel.css"', 'href="/panel/panel.css"')
        html = html.replace('<script src="clip.js"></script>',
                            '<link rel="stylesheet" href="/static/web.css">\n  <script src="/static/web.js"></script>\n  <script src="/panel/clip.js"></script>')
        html = html.replace('<script src="panel.js"></script>', '<script src="/panel/panel.js"></script>')
        _panel_html = html
    return _panel_html


async def panel_page(request: Request):
    sid = request.path_params["sid"]
    if not me(request):
        return RedirectResponse("/", 303)
    if sid not in store.state["servers"]:
        return RedirectResponse("/", 303)
    html = panel_html().replace("<head>", '<head>\n  <meta name="nx-server" content="%s">' % sid, 1)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


async def health(request: Request):
    return JSONResponse({"ok": True, "servers": {sid: hub.link(sid).online for sid in store.state["servers"]}})


# ------------------------------------------------------------- setup / login
async def api_setup(request: Request):
    if store.state["users"]:
        return fail("Already set up.", 403)
    if request.headers.get("x-nx") != "1":
        return fail("Bad request.", 403)
    data = await body_json(request)
    name, pw = str(data.get("username", "")), str(data.get("password", ""))
    if not NAME_RE.match(name):
        return fail("Username: 3-32 letters, numbers, . _ -")
    if len(pw) < 10:
        return fail("Password: at least 10 characters.")
    store.state["users"][name] = {"hash": auth.hash_password(pw), "role": "owner", "v": 0, "created": int(time.time())}
    await store.save()
    return set_session(ok(), name)


async def api_login(request: Request):
    if request.headers.get("x-nx") != "1":
        return fail("Bad request.", 403)
    ip = request.client.host if request.client else "?"
    if not limiter.allow("login:" + ip, 10, 300):
        return fail("Too many attempts. Wait a few minutes.", 429)
    data = await body_json(request)
    name, pw = str(data.get("username", "")), str(data.get("password", ""))
    user = store.state["users"].get(name)
    # Hash even for unknown names so timing does not reveal which exist.
    good = auth.check_password(pw, user["hash"] if user else "scrypt$00$00")
    if not user or not good:
        return fail("Wrong username or password.", 401)
    return set_session(ok(), name)


async def api_logout(request: Request):
    resp = ok()
    resp.delete_cookie(auth.COOKIE, path="/")
    return resp


@guarded()
async def api_me(request: Request):
    u = request.state.user
    servers = [{"id": sid, "name": s["name"], "online": hub.link(sid).online, "info": hub.link(sid).info,
                "keyPrefix": s.get("keyPrefix", "") if u["role"] == "owner" else None}
               for sid, s in store.state["servers"].items()]
    users = None
    if u["role"] == "owner":
        users = [{"username": n, "role": x["role"]} for n, x in store.state["users"].items()]
    return ok(user={"username": u["username"], "role": u["role"]}, servers=servers, users=users, roles=auth.ROLES)


# ------------------------------------------------------- owner: servers/users
@guarded(owner_only=True)
async def api_server_create(request: Request):
    data = await body_json(request)
    name = str(data.get("name", "")).strip()[:60]
    if not name:
        return fail("Give the server a name.")
    key, digest = auth.new_server_key()
    sid = secrets.token_hex(6)
    store.state["servers"][sid] = {"name": name, "keyHash": digest, "keyPrefix": key[:6], "created": int(time.time())}
    await store.save()
    return ok(id=sid, key=key)


@guarded(owner_only=True)
async def api_server_rotate(request: Request):
    sid = request.path_params["sid"]
    s = store.state["servers"].get(sid)
    if not s:
        return fail("Unknown server.", 404)
    key, digest = auth.new_server_key()
    s["keyHash"], s["keyPrefix"] = digest, key[:6]
    await store.save()
    return ok(key=key)


@guarded(owner_only=True)
async def api_server_delete(request: Request):
    sid = request.path_params["sid"]
    if store.state["servers"].pop(sid, None) is None:
        return fail("Unknown server.", 404)
    hub.links.pop(sid, None)
    await store.save()
    return ok()


@guarded(owner_only=True)
async def api_user_save(request: Request):
    data = await body_json(request)
    name, role, pw = str(data.get("username", "")), str(data.get("role", "")), data.get("password")
    if not NAME_RE.match(name):
        return fail("Username: 3-32 letters, numbers, . _ -")
    if role not in auth.ROLES:
        return fail("Unknown role.")
    users = store.state["users"]
    user = users.get(name)
    if user is None:
        if not isinstance(pw, str) or len(pw) < 10:
            return fail("Password: at least 10 characters.")
        users[name] = {"hash": auth.hash_password(pw), "role": role, "v": 0, "created": int(time.time())}
    else:
        if name == request.state.user["username"] and role != "owner":
            return fail("You cannot take owner away from yourself.")
        user["role"] = role
        if isinstance(pw, str) and pw:
            if len(pw) < 10:
                return fail("Password: at least 10 characters.")
            user["hash"] = auth.hash_password(pw)
            user["v"] = user.get("v", 0) + 1
    await store.save()
    return ok()


@guarded(owner_only=True)
async def api_user_delete(request: Request):
    name = request.path_params["name"]
    if name == request.state.user["username"]:
        return fail("You cannot delete yourself.")
    if store.state["users"].pop(name, None) is None:
        return fail("Unknown user.", 404)
    await store.save()
    return ok()


@guarded()
async def api_password(request: Request):
    data = await body_json(request)
    u = store.state["users"][request.state.user["username"]]
    if not auth.check_password(str(data.get("current", "")), u["hash"]):
        return fail("Current password is wrong.")
    pw = str(data.get("password", ""))
    if len(pw) < 10:
        return fail("Password: at least 10 characters.")
    u["hash"], u["v"] = auth.hash_password(pw), u.get("v", 0) + 1
    await store.save()
    return set_session(ok(), request.state.user["username"])


# ------------------------------------------------------------- panel transport
@guarded()
async def api_query(request: Request):
    """One panel request (open / section / exec), answered by the game server."""
    sid = request.path_params["sid"]
    if sid not in store.state["servers"]:
        return fail("Unknown server.", 404)
    u = request.state.user
    data = await body_json(request)
    kind = data.get("kind")
    if kind not in ("open", "section", "exec"):
        return fail("Bad request.")
    if kind == "exec":
        if not limiter.allow("x:" + u["username"], 6, 1.0):
            return JSONResponse({"ok": False, "msg": "Slow down a moment."})
    elif not limiter.allow("s:" + u["username"], 30, 1.0):
        return JSONResponse({"ok": False, "msg": "Slow down a moment."})
    job = {"kind": kind, "role": u["role"], "user": u["username"]}
    if kind == "section":
        job["section"], job["arg"] = str(data.get("section", ""))[:40], data.get("arg")
    elif kind == "exec":
        if not isinstance(data.get("cmd"), dict):
            return fail("Bad request.")
        job["cmd"] = data["cmd"]
    return JSONResponse(await hub.ask(sid, job))


# ------------------------------------------------------------------ the bridge
def server_for_key(header: str | None) -> str | None:
    if not header or not header.startswith("Bearer "):
        return None
    digest = auth.key_hash(header[7:].strip())
    for sid, s in store.state["servers"].items():
        if hmac.compare_digest(s["keyHash"], digest):
            return sid
    return None


async def api_bridge(request: Request):
    sid = server_for_key(request.headers.get("authorization"))
    if not sid:
        return fail("Unknown key.", 401)
    raw = await request.body()
    if len(raw) > MAX_BRIDGE_BODY:
        return fail("Too large.", 413)
    try:
        body = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return fail("Bad JSON.")
    jobs = await hub.bridge(sid, body if isinstance(body, dict) else {})
    return JSONResponse({"ok": True, "jobs": jobs})


# --------------------------------------------------------------------- the app
@contextlib.asynccontextmanager
async def lifespan(app):
    await store.load()
    yield


routes = [
    Route("/", index),
    Route("/s/{sid}", panel_page),
    Route("/health", health),
    Route("/api/setup", api_setup, methods=["POST"]),
    Route("/api/login", api_login, methods=["POST"]),
    Route("/api/logout", api_logout, methods=["POST"]),
    Route("/api/me", api_me),
    Route("/api/password", api_password, methods=["POST"]),
    Route("/api/servers", api_server_create, methods=["POST"]),
    Route("/api/servers/{sid}/rotate", api_server_rotate, methods=["POST"]),
    Route("/api/servers/{sid}", api_server_delete, methods=["DELETE"]),
    Route("/api/users", api_user_save, methods=["POST"]),
    Route("/api/users/{name}", api_user_delete, methods=["DELETE"]),
    Route("/api/s/{sid}/q", api_query, methods=["POST"]),
    Route("/api/bridge", api_bridge, methods=["POST"]),
    Mount("/panel", StaticFiles(directory=PANEL), name="panel"),
    Mount("/static", StaticFiles(directory=HERE / "static"), name="static"),
]

app = Starlette(routes=routes, lifespan=lifespan)
