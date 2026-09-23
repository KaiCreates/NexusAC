"""The JSON API the website's own pages call. Everything here is cookie
authenticated and origin checked; the bridge is the one exception and lives in
bridge.py."""
from __future__ import annotations

import base64
import re
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from . import (
    db, events as event_store, identities as identity_store,
    punishments as punishment_store, supabase_auth,
)
from .bridge import handle as bridge_handle, json_body
from .protocol import parse_command
from .security import (
    HttpError, PERMISSIONS, audit, authenticated, create_session, new_id, new_secret, now,
    origin_check, rate, reply, require, set_session_cookie, sha256, token_from,
)

router = APIRouter()
EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")
MIN_PASSWORD = 12
ONLINE_WINDOW = 30  # the resource heartbeats about once per second


def _online(last_seen: Any) -> bool:
    return last_seen is not None and now() - int(last_seen) < ONLINE_WINDOW


# --------------------------------------------------------------------------- #
# Bridge
# --------------------------------------------------------------------------- #

@router.post("/bridge/{action}")
async def bridge(request: Request, action: str):
    return await bridge_handle(request, action)


# --------------------------------------------------------------------------- #
# Accounts
# --------------------------------------------------------------------------- #

@router.post("/auth/{action}")
async def auth(request: Request, action: str):
    origin_check(request)
    if action == "logout":
        response = reply({"ok": True})
        db.execute("DELETE FROM nx_sessions WHERE hash=%s", (sha256(token_from(request)),))
        set_session_cookie(response, "", clear=True)
        return response

    require(action in ("register", "login"), 404, "Unknown authentication action.")
    form = await json_body(request, 32_000)
    email = str(form.get("email", "")).strip().lower()
    password = str(form.get("password", ""))
    name = str(form.get("name", "")).strip()[:80]

    require(EMAIL.match(email) and len(email) <= 254, 400, "Enter a valid email address.")
    require(len(password) >= MIN_PASSWORD, 400,
            "Use a password of at least %d characters." % MIN_PASSWORD)
    rate("auth:global", 300, 60)
    rate("auth:" + email, 12)

    if action == "register":
        result = supabase_auth.sign_up(email, password, name or "Owner")
        if result.get("confirm"):
            return reply({
                "ok": True,
                "confirm": True,
                "message": "Check your email to confirm the account, then sign in.",
            })
        identity = result["identity"]
    else:
        identity = supabase_auth.sign_in(email, password)

    user_id = identity["id"]
    if not db.one("SELECT id FROM nx_users WHERE id=%s", (user_id,)):
        # First sign-in for this Supabase account: give it a user row, a workspace,
        # and ownership of that workspace.
        workspace = new_id()
        with db.transaction() as cur:
            cur.execute(
                "INSERT INTO nx_users VALUES(%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING",
                (user_id, email, name or email.split("@")[0], now()),
            )
            cur.execute(
                "INSERT INTO nx_workspaces VALUES(%s,%s,%s)",
                (workspace, (name or "My") + " workspace", now()),
            )
            cur.execute("INSERT INTO nx_members VALUES(%s,%s,'owner')", (workspace, user_id))

    membership = db.one(
        "SELECT workspace FROM nx_members WHERE user_id=%s ORDER BY (role='owner') DESC LIMIT 1",
        (user_id,),
    )
    require(membership, 500, "Your account has no workspace.")

    token = create_session(user_id, str(membership["workspace"]))
    response = reply({"ok": True})
    set_session_cookie(response, token)
    return response


@router.post("/reset")
async def reset(request: Request):
    origin_check(request)
    form = await json_body(request, 8_000)
    email = str(form.get("email", "")).strip().lower()
    if EMAIL.match(email):
        rate("reset:" + email, 4)
        supabase_auth.send_password_reset(email)
    # Always the same answer, so this cannot be used to discover which emails exist.
    return reply({"ok": True, "message": "If that account exists, a reset email is on its way."})


# --------------------------------------------------------------------------- #
# Workspace
# --------------------------------------------------------------------------- #

@router.get("/workspace")
async def workspace(request: Request):
    user = authenticated(request)
    space = user["workspace"]
    servers = db.query(
        "SELECT id,name,last_seen,created,token_hint FROM nx_servers "
        "WHERE workspace=%s ORDER BY created", (space,),
    )
    members = db.query(
        "SELECT u.id,u.name,u.email,m.role FROM nx_members m "
        "JOIN nx_users u ON m.user_id=u.id WHERE m.workspace=%s ORDER BY m.role", (space,),
    )
    commands = db.query(
        "SELECT c.id,c.server,c.actor_name,c.body,c.created,c.expires,c.status,c.result "
        "FROM nx_commands c JOIN nx_servers s ON c.server=s.id "
        "WHERE s.workspace=%s ORDER BY c.created DESC LIMIT 100", (space,),
    )
    logs = db.query(
        "SELECT id,actor,action,detail,at FROM nx_audit WHERE workspace=%s ORDER BY at DESC LIMIT 100",
        (space,),
    )
    spaces = db.query(
        "SELECT w.id,w.name FROM nx_workspaces w JOIN nx_members m ON w.id=m.workspace "
        "WHERE m.user_id=%s", (user["user_id"],),
    )
    return reply({
        "user": {
            "id": str(user["user_id"]), "name": user["name"],
            "email": user["email"], "role": user["role"], "workspace": str(space),
        },
        "servers": [
            {"id": str(s["id"]), "name": s["name"], "lastSeen": s["last_seen"],
             "created": s["created"], "hint": s["token_hint"], "online": _online(s["last_seen"])}
            for s in servers
        ],
        "members": [{"id": str(m["id"]), "name": m["name"], "email": m["email"],
                     "role": m["role"]} for m in members],
        "commands": [
            {"id": str(c["id"]), "server": str(c["server"]), "actor": c["actor_name"],
             "body": c["body"], "created": c["created"], "expires": c["expires"],
             "result": c["result"],
             "status": "expired" if c["status"] in ("pending", "sent")
                       and int(c["expires"]) <= now() else c["status"]}
            for c in commands
        ],
        "audit": [{"id": str(a["id"]), "actor": a["actor"], "action": a["action"],
                   "detail": a["detail"], "at": a["at"]} for a in logs],
        "workspaces": [{"id": str(s["id"]), "name": s["name"]} for s in spaces],
        "serverTime": now(),
    })


@router.post("/workspace/switch")
async def switch(request: Request):
    origin_check(request)
    user = authenticated(request)
    target = str((await json_body(request, 4_000)).get("id", ""))
    require(
        db.one("SELECT role FROM nx_members WHERE workspace=%s AND user_id=%s",
               (target, user["user_id"])),
        403, "Workspace access denied.",
    )
    db.execute("UPDATE nx_sessions SET workspace=%s WHERE hash=%s",
               (target, sha256(token_from(request))))
    return reply({"ok": True})


@router.post("/staff/{action}")
async def staff(request: Request, action: str):
    origin_check(request)
    user = authenticated(request)
    require(user["role"] == "owner", 403, "Only the workspace owner can manage staff.")
    form = await json_body(request, 8_000)

    if action == "invite":
        role = str(form.get("role", ""))
        require(role in ("administrator", "moderator", "viewer"), 400, "Unknown role.")
        rate("invite:" + str(user["workspace"]), 20)
        token = new_secret()
        db.execute("INSERT INTO nx_invites VALUES(%s,%s,%s,%s,%s)",
                   (sha256(token), user["workspace"], role, now() + 86400, user["user_id"]))
        audit(user, "staff.invite", role)
        return reply({"token": token, "expires": now() + 86400})

    if action == "add":
        # Add someone who already has a NexusAC account, by username or email.
        # Falls back to an invite code when there is no such account yet, so the
        # answer is never a dead end.
        identifier = str(form.get("identifier", "")).strip()
        role = str(form.get("role", ""))
        require(identifier, 400, "Enter a username or email address.")
        require(role in ("administrator", "moderator", "viewer"), 400, "Unknown role.")
        rate("staffadd:" + str(user["workspace"]), 30)

        matches = db.query(
            "SELECT id, name, email FROM nx_users WHERE lower(email)=lower(%s) OR lower(name)=lower(%s)",
            (identifier, identifier),
        )
        if not matches:
            token = new_secret()
            db.execute("INSERT INTO nx_invites VALUES(%s,%s,%s,%s,%s)",
                       (sha256(token), user["workspace"], role, now() + 86400, user["user_id"]))
            audit(user, "staff.invite", role + " (no account for " + identifier[:60] + ")")
            return reply({
                "invited": True, "token": token, "expires": now() + 86400,
                "message": "Nobody with that username or email has an account yet. "
                           "Send them this code — it works once, for 24 hours.",
            })
        # A display name is not unique; refuse rather than guess who was meant.
        require(len(matches) == 1, 409,
                "More than one account uses that username. Use their email address instead.")

        target = matches[0]
        require(str(target["id"]) != str(user["user_id"]), 409, "That is your own account.")
        existing = db.one("SELECT role FROM nx_members WHERE workspace=%s AND user_id=%s",
                          (user["workspace"], target["id"]))
        if existing:
            raise HttpError(409, "%s is already in this workspace as %s."
                                 % (target["name"], existing["role"]))
        db.execute("INSERT INTO nx_members VALUES(%s,%s,%s)",
                   (user["workspace"], target["id"], role))
        audit(user, "staff.add", target["name"] + " (" + target["email"] + ") as " + role)
        return reply({"added": True, "name": target["name"], "email": target["email"], "role": role})

    if action == "remove":
        target = str(form.get("userId", ""))
        db.execute("DELETE FROM nx_members WHERE workspace=%s AND user_id=%s AND role<>'owner'",
                   (user["workspace"], target))
        audit(user, "staff.remove", target)
        return reply({"ok": True})

    if action == "revoke-invites":
        db.execute("DELETE FROM nx_invites WHERE workspace=%s", (user["workspace"],))
        audit(user, "staff.revoke", "all pending invitations")
        return reply({"ok": True})

    raise HttpError(404, "Unknown staff action.")


@router.post("/invite/accept")
async def accept_invite(request: Request):
    origin_check(request)
    user = authenticated(request)
    token = str((await json_body(request, 4_000)).get("token", ""))
    require(len(token) == 43, 400, "That invitation code is not valid.")
    with db.transaction() as cur:
        cur.execute("DELETE FROM nx_invites WHERE hash=%s AND expires>%s RETURNING workspace, role",
                    (sha256(token), now()))
        invite = cur.fetchone()
        require(invite, 400, "Invitation is invalid, expired, or already used.")
        cur.execute(
            "INSERT INTO nx_members VALUES(%s,%s,%s) ON CONFLICT(workspace,user_id) DO NOTHING",
            (invite["workspace"], user["user_id"], invite["role"]),
        )
        cur.execute("UPDATE nx_sessions SET workspace=%s WHERE hash=%s",
                    (invite["workspace"], sha256(token_from(request))))
    return reply({"ok": True})


# --------------------------------------------------------------------------- #
# Servers and API keys
# --------------------------------------------------------------------------- #

@router.post("/servers")
async def create_server(request: Request):
    origin_check(request)
    user = authenticated(request)
    require(user["role"] == "owner", 403, "Only the owner can add a server.")
    name = str((await json_body(request, 4_000)).get("name", "")).strip()[:80]
    require(name, 400, "Give the server a name.")
    count = db.one("SELECT count(*) AS n FROM nx_servers WHERE workspace=%s", (user["workspace"],))
    require(int(count["n"]) < 50, 409, "Workspace server limit reached.")

    server_id, token = new_id(), new_secret()
    db.execute(
        "INSERT INTO nx_servers(id,workspace,name,token_hash,token_hint,created) "
        "VALUES(%s,%s,%s,%s,%s,%s)",
        (server_id, user["workspace"], name, sha256(token), token[:6], now()),
    )
    audit(user, "server.create", name)
    return reply({"id": server_id, "token": token}, 201)


# --------------------------------------------------------------------------- #
# Identities
#
# Read-only and workspace scoped. Identifiers are addressed as query parameters
# rather than path segments because a uid looks like `license:9f3a...` and a raw
# colon in a path is a needless escaping problem for every caller.
# --------------------------------------------------------------------------- #

def _int_param(request: Request, name: str, default: int) -> int:
    raw = request.query_params.get(name)
    try:
        return int(raw) if raw is not None else default
    except ValueError:
        return default


@router.get("/identities")
async def identity_search(request: Request):
    user = authenticated(request)
    rate(f"identities:{user['id']}", 120, 60)
    return reply(
        identity_store.search(
            user["workspace"],
            request.query_params.get("q", ""),
            _int_param(request, "page", 1),
            _int_param(request, "size", 25),
        )
    )


@router.get("/identities/detail")
async def identity_detail(request: Request):
    user = authenticated(request)
    uid = request.query_params.get("uid", "")
    require(uid, 400, "An identity id is required.")
    return reply(identity_store.detail(user["workspace"], uid))


@router.get("/identities/aliases")
async def identity_aliases(request: Request):
    user = authenticated(request)
    uid = request.query_params.get("uid", "")
    require(uid, 400, "An identity id is required.")
    # The traversal is several indexed queries deep, so it gets a tighter budget
    # than the plain search above.
    rate(f"aliases:{user['id']}", 30, 60)
    return reply(
        identity_store.aliases(
            user["workspace"], uid, _int_param(request, "depth", identity_store.MAX_DEPTH)
        )
    )


# --------------------------------------------------------------------------- #
# Event log
# --------------------------------------------------------------------------- #

@router.get("/events")
async def events_search(request: Request):
    user = authenticated(request)
    rate(f"events:{user['id']}", 180, 60)
    q = request.query_params
    return reply(
        event_store.search(
            user["workspace"],
            q.get("q", ""),
            q.get("type"),
            q.get("window", "all"),
            _int_param(request, "page", 1),
            _int_param(request, "size", 25),
            q.get("server") or None,
        )
    )


@router.get("/events/types")
async def events_types(request: Request):
    user = authenticated(request)
    return reply({"types": event_store.types(user["workspace"])})


# --------------------------------------------------------------------------- #
# Punishments
# --------------------------------------------------------------------------- #

@router.get("/punishments")
async def punishments_search(request: Request):
    user = authenticated(request)
    rate(f"punishments:{user['id']}", 180, 60)
    q = request.query_params
    result = punishment_store.search(
        user["workspace"],
        q.get("q", ""),
        q.get("kind"),
        q.get("window", "all"),
        q.get("actor"),
        _int_param(request, "page", 1),
        _int_param(request, "size", 25),
    )
    result["summary"] = punishment_store.summary(user["workspace"])
    return reply(result)


@router.get("/punishments/identity")
async def punishments_for_identity(request: Request):
    user = authenticated(request)
    identifier = request.query_params.get("uid", "")
    require(identifier, 400, "An identity id is required.")
    return reply({"rows": punishment_store.for_identity(user["workspace"], identifier)})


def _server_of(user: dict, server_id: str) -> dict:
    try:
        server = db.one("SELECT * FROM nx_servers WHERE id=%s AND workspace=%s",
                        (server_id, user["workspace"]))
    except Exception:
        server = None  # a malformed uuid in the path is a 404, not a 500
    require(server, 404, "Server not found.")
    return server


@router.post("/servers/{server_id}/rotate")
async def rotate(request: Request, server_id: str):
    origin_check(request)
    user = authenticated(request)
    require(user["role"] == "owner", 403, "Only the owner can rotate an API key.")
    server = _server_of(user, server_id)
    token = new_secret()
    with db.transaction() as cur:
        cur.execute(
            "UPDATE nx_servers SET token_hash=%s, token_hint=%s, last_seen=NULL, boot=NULL, "
            "sequence=0 WHERE id=%s",
            (sha256(token), token[:6], server_id),
        )
        cur.execute(
            "UPDATE nx_commands SET status='cancelled', result='API key rotated.' "
            "WHERE server=%s AND status IN ('pending','sent')",
            (server_id,),
        )
    audit(user, "server.rotate", str(server["name"]))
    return reply({"id": server_id, "token": token})


@router.post("/servers/{server_id}/delete")
async def delete_server(request: Request, server_id: str):
    origin_check(request)
    user = authenticated(request)
    require(user["role"] == "owner", 403, "Only the owner can remove a server.")
    server = _server_of(user, server_id)
    db.execute("DELETE FROM nx_servers WHERE id=%s", (server_id,))
    audit(user, "server.delete", str(server["name"]))
    return reply({"ok": True})


@router.get("/servers/{server_id}/snapshot")
async def snapshot(request: Request, server_id: str):
    user = authenticated(request)
    server = _server_of(user, server_id)
    evidence = db.query(
        "SELECT e.id, e.body, (SELECT count(*) FROM nx_media m "
        "WHERE m.server=e.server AND m.evidence_id=e.id) AS images "
        "FROM nx_evidence e WHERE e.server=%s ORDER BY e.updated DESC LIMIT 200",
        (server_id,),
    )
    # Recent commands travel with the snapshot. Without them this page could
    # only ever say "queued" -- a refused or failed command was invisible here,
    # because commands were only exposed on the workspace endpoint.
    commands = db.query(
        "SELECT id, actor_name, body, created, expires, status, result, ack_at "
        "FROM nx_commands WHERE server=%s ORDER BY created DESC LIMIT 25",
        (server_id,),
    )

    return reply({
        "id": server_id,
        "name": server["name"],
        "role": user["role"],
        "hint": server["token_hint"],
        "lastSeen": server["last_seen"],
        "online": _online(server["last_seen"]),
        "serverTime": now(),
        "snapshot": server["snapshot"],
        "evidence": [dict(e["body"], images=int(e["images"])) for e in evidence],
        "commands": [
            {
                "id": str(c["id"]),
                "actor": c["actor_name"],
                "type": (c["body"] or {}).get("type"),
                "path": (c["body"] or {}).get("path") or (c["body"] or {}).get("detector")
                        or (c["body"] or {}).get("signal"),
                "value": (c["body"] or {}).get("value") or (c["body"] or {}).get("mode")
                         or (c["body"] or {}).get("action"),
                "created": int(c["created"]),
                "result": c["result"],
                "ackAt": c["ack_at"],
                "status": "expired" if c["status"] in ("pending", "sent")
                          and int(c["expires"]) <= now() else c["status"],
            }
            for c in commands
        ],
    })


@router.post("/servers/{server_id}/commands")
async def command(request: Request, server_id: str):
    origin_check(request)
    user = authenticated(request)
    server = _server_of(user, server_id)
    payload = parse_command(await json_body(request, 16_000))
    kind = payload.type

    require(kind in PERMISSIONS.get(user["role"], ()), 403,
            "Your role cannot perform this action.")
    require(_online(server["last_seen"]), 409,
            "Server is offline. Reconnect it before sending commands.")
    snap = server["snapshot"] or {}

    # Every mutating command carries the value it expects to be acting on. If the
    # world moved since the page was drawn, the command is refused rather than
    # applied to whatever is there now.
    if kind in ("warn", "kick", "ban", "freeze", "screenshot"):
        require(
            any(p.get("src") == payload.target and p.get("sessionKey") == payload.session
                for p in snap.get("players", [])),
            409, "That player's session changed. Refresh the player list.",
        )
    elif kind == "unban":
        require(any(b.get("identifier") == payload.identifier for b in snap.get("bans", [])),
                409, "That ban no longer exists.")
    elif kind == "setting":
        setting = (snap.get("config") or {}).get("settings", {}).get(payload.path)
        require(setting and setting.get("value") == payload.expected, 409,
                "That setting changed. Refresh before editing.")
    elif kind == "detector":
        detector = next((d for d in snap.get("detectors", [])
                         if d.get("id") == payload.detector), None)
        require(detector and not detector.get("locked")
                and detector.get("mode") == payload.expected,
                409, "That detector is locked, unknown, or changed.")
    elif kind == "punish":
        row = next((k for k in (snap.get("config") or {}).get("kinds", [])
                    if k.get("kind") == payload.signal), None)
        require(row and row.get("action") == payload.expected, 409,
                "That signal is unknown, or its punishment changed. Refresh before editing.")

    rate("command:" + str(user["user_id"]), 60, 60)
    command_id = new_id()
    db.execute(
        "INSERT INTO nx_commands(id,server,actor,actor_name,body,created,expires) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (command_id, server_id, user["user_id"], user["name"],
         db.jsonb(payload.model_dump(mode="json")), now(), now() + 60),
    )
    audit(user, "command." + kind, str(server["name"]) + " / " + command_id)
    return reply({"id": command_id, "status": "pending"}, 202)


@router.get("/servers/{server_id}/media/{evidence_id}/{slot}")
async def media(request: Request, server_id: str, evidence_id: str, slot: int):
    user = authenticated(request)
    _server_of(user, server_id)
    require(0 <= slot <= 2, 400, "Invalid screenshot slot.")
    row = db.one("SELECT data FROM nx_media WHERE server=%s AND evidence_id=%s AND slot=%s",
                 (server_id, evidence_id, slot))
    require(row, 404, "Screenshot not available.")
    return Response(
        base64.b64decode(str(row["data"]).split(",", 1)[1]),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )
