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
    db, disconnects as disconnect_store, events as event_store, identities as identity_store,
    punishments as punishment_store, supabase_auth,
)
from .bridge import handle as bridge_handle, json_body
from .protocol import StreamFramesRequest, parse_command
from .security import (
    HttpError, PERMISSIONS, audit, authenticated, create_session, new_id, new_secret, now,
    origin_check, rate, reply, require, set_session_cookie, sha256, token_from,
)

router = APIRouter()
EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")
MIN_PASSWORD = 12
DEGRADED_WINDOW = 30
ONLINE_WINDOW = 60


def _online(last_seen: Any) -> bool:
    return last_seen is not None and now() - int(last_seen) < ONLINE_WINDOW


def _health(last_seen: Any) -> str:
    if last_seen is None:
        return "offline"
    age = max(0, now() - int(last_seen))
    if age < DEGRADED_WINDOW:
        return "online"
    if age < ONLINE_WINDOW:
        return "degraded"
    return "offline"


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
             "created": s["created"], "hint": s["token_hint"], "online": _online(s["last_seen"]),
             "status": _health(s["last_seen"])}
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
    require(user["role"] in ("owner", "administrator"), 403,
            "Only owners and administrators can view network identity data.")
    rate(f"identities:{user['user_id']}", 120, 60)
    db.ensure_schema()
    return reply(
        identity_store.search(
            user["workspace"],
            request.query_params.get("q", ""),
            _int_param(request, "page", 1),
            _int_param(request, "size", 25),
        )
    )


@router.get("/identities/online")
async def identities_online(request: Request):
    """Live, workspace-scoped players for the Identities network page."""
    user = authenticated(request)
    require(user["role"] in ("owner", "administrator"), 403,
            "Only owners and administrators can view network identity data.")
    rate(f"identities-online:{user['user_id']}", 120, 60)
    servers = db.query(
        "SELECT id,name,last_seen,snapshot FROM nx_servers WHERE workspace=%s ORDER BY name",
        (user["workspace"],),
    )
    rows = []
    online_servers = 0
    for server in servers:
        if not _online(server["last_seen"]):
            continue
        online_servers += 1
        snapshot = server.get("snapshot") or {}
        for player in snapshot.get("players", []):
            rows.append({
                "server": server["name"],
                "src": player.get("src"),
                "name": player.get("name") or "Unknown",
                "ping": player.get("ping"),
                "risk": player.get("risk"),
                "sessionAge": player.get("sessionAge"),
                "network": player.get("network") or {},
            })
    return reply({"players": rows, "servers": online_servers, "updatedAt": now()})


@router.get("/identities/summary")
async def identities_summary(request: Request):
    user = authenticated(request)
    require(user["role"] in ("owner", "administrator"), 403,
            "Only owners and administrators can view network identity data.")
    db.ensure_schema()
    return reply(identity_store.summary(user["workspace"]))


@router.get("/identities/detail")
async def identity_detail(request: Request):
    user = authenticated(request)
    require(user["role"] in ("owner", "administrator"), 403,
            "Only owners and administrators can view network identity data.")
    db.ensure_schema()
    uid = request.query_params.get("uid", "")
    require(uid, 400, "An identity id is required.")
    return reply(identity_store.detail(user["workspace"], uid))


@router.get("/identities/aliases")
async def identity_aliases(request: Request):
    user = authenticated(request)
    require(user["role"] in ("owner", "administrator"), 403,
            "Only owners and administrators can view network identity data.")
    db.ensure_schema()
    uid = request.query_params.get("uid", "")
    require(uid, 400, "An identity id is required.")
    # The traversal is several indexed queries deep, so it gets a tighter budget
    # than the plain search above.
    rate(f"aliases:{user['user_id']}", 30, 60)
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
    rate(f"events:{user['user_id']}", 180, 60)
    db.ensure_schema()
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
    db.ensure_schema()
    return reply({"types": event_store.types(user["workspace"])})


# --------------------------------------------------------------------------- #
# Punishments
# --------------------------------------------------------------------------- #

@router.get("/punishments")
async def punishments_search(request: Request):
    user = authenticated(request)
    rate(f"punishments:{user['user_id']}", 180, 60)
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
    # The dashboard polls this every couple of seconds. It used to send the
    # whole server snapshot and the last 200 evidence records every time --
    # around a megabyte a poll, for data the game server only changes every
    # 30 s -- which emptied Render's 5 GB monthly bandwidth in an afternoon.
    # Now the page sends the versions it already holds (sv, ev) and gets back
    # only the parts that changed. Both versions are computed in the
    # database, so an unchanged poll moves a few hundred bytes end to end.
    user = authenticated(request)
    try:
        server = db.one(
            "SELECT id, name, token_hint, last_seen, sequence FROM nx_servers "
            "WHERE id=%s AND workspace=%s", (server_id, user["workspace"]))
    except Exception:
        server = None
    require(server, 404, "Server not found.")
    snapshot_version = "%s:%s:%s" % (server["last_seen"], server["sequence"], user["role"])
    ev_meta = db.one(
        "SELECT md5(coalesce(string_agg(e.id::text || md5(e.body::text), ',' ORDER BY e.id::text), '')) AS v, "
        "(SELECT count(*) FROM nx_media m WHERE m.server=%s) AS media "
        "FROM (SELECT id, body FROM nx_evidence WHERE server=%s "
        "ORDER BY (body->>'at')::double precision DESC, id DESC LIMIT 200) e",
        (server_id, server_id),
    )
    evidence_version = "%s:%s" % (ev_meta["v"], ev_meta["media"])
    send_snapshot = request.query_params.get("sv") != snapshot_version
    send_evidence = request.query_params.get("ev") != evidence_version
    if send_snapshot:
        row = db.one("SELECT snapshot FROM nx_servers WHERE id=%s", (server_id,))
        server["snapshot"] = row["snapshot"] if row else None
    evidence = db.query(
        "SELECT e.id, e.body, (SELECT count(*) FROM nx_media m "
        "WHERE m.server=e.server AND m.evidence_id=e.id) AS images "
        "FROM nx_evidence e WHERE e.server=%s "
        "ORDER BY (e.body->>'at')::double precision DESC, e.id DESC LIMIT 200",
        (server_id,),
    ) if send_evidence else []
    # Recent commands travel with the snapshot. Without them this page could
    # only ever say "queued" -- a refused or failed command was invisible here,
    # because commands were only exposed on the workspace endpoint.
    commands = db.query(
        "SELECT id, actor_name, body, created, expires, status, result, ack_at "
        "FROM nx_commands WHERE server=%s ORDER BY created DESC LIMIT 25",
        (server_id,),
    )

    public_snapshot = (server.get("snapshot") or {}) if send_snapshot else {}
    if send_snapshot and user["role"] not in ("owner", "administrator"):
        # The server snapshot is shared across workspace roles. Never rely on
        # the browser to hide identifiers/IPs: strip them at the API boundary.
        public_snapshot = dict(public_snapshot)
        public_snapshot["players"] = [
            {**player, "network": None} for player in public_snapshot.get("players", [])
        ]

    return reply({
        "id": server_id,
        "name": server["name"],
        "role": user["role"],
        "hint": server["token_hint"],
        "lastSeen": server["last_seen"],
        "online": _online(server["last_seen"]),
        "status": _health(server["last_seen"]),
        "serverTime": now(),
        "snapshotVersion": snapshot_version,
        "evidenceVersion": evidence_version,
        "snapshotUnchanged": not send_snapshot,
        "evidenceUnchanged": not send_evidence,
        "snapshot": public_snapshot if send_snapshot else None,
        "evidence": [dict(e["body"], images=int(e["images"])) for e in evidence] if send_evidence else None,
        "commands": [
            {
                "id": str(c["id"]),
                "actor": c["actor_name"],
                "type": (c["body"] or {}).get("type"),
                "path": (c["body"] or {}).get("path") or (c["body"] or {}).get("detector")
                        or (c["body"] or {}).get("id") or (c["body"] or {}).get("category")
                        or (c["body"] or {}).get("signal") or (c["body"] or {}).get("model"),
                # Boolean false is a real setting value, not a missing value.
                # Using an `or` chain made every "turn off" command appear in
                # the audit panel with a blank value even when it succeeded.
                "value": next(((c["body"] or {})[key] for key in
                               ("value", "mode", "action", "policy", "enabled")
                               if key in (c["body"] or {})), None),
                "created": int(c["created"]),
                "result": c["result"],
                "ackAt": c["ack_at"],
                "status": "expired" if c["status"] in ("pending", "sent")
                          and int(c["expires"]) <= now() else c["status"],
            }
            for c in commands
        ],
    })


@router.get("/servers/{server_id}/disconnects")
async def server_disconnects(request: Request, server_id: str):
    """Why players left: classified drops, crash signatures, mass disconnects."""
    user = authenticated(request)
    rate(f"disconnects:{user['user_id']}", 60, 60)
    _server_of(user, server_id)
    db.ensure_schema()
    return reply(disconnect_store.summary(
        user["workspace"], server_id, request.query_params.get("window", "24h")))


@router.get("/servers/{server_id}/activity")
async def server_activity(request: Request, server_id: str):
    """Hourly (24h) or 6-hourly (7d) event counts for the Overview chart."""
    user = authenticated(request)
    rate(f"activity:{user['user_id']}", 60, 60)
    _server_of(user, server_id)
    db.ensure_schema()
    return reply(event_store.activity(
        user["workspace"], server_id, request.query_params.get("window", "24h")))


# How long a queued command may wait for the game server to collect it.
#
# Configuration used to share the 60 s window meant for kicks and bans. One
# slow or failed bridge sync (a cold Render worker, a 429, a rejected payload)
# and every settings change expired unseen -- the page then fell back to the
# server's real value, which looked like options "turning themselves back on"
# every minute, and nothing was ever written to the server's config file.
#
# Configuration is safe to deliver late: every config command carries the
# value it expects to replace, and the resource refuses it if that value has
# changed since (sv_panel.lua webExecute). Moderation actions are not -- a kick
# arriving ten minutes later is a different act -- so they keep 60 s.
CONFIG_KINDS = {"setting", "detector", "protection", "punish", "webhook", "eventRule", "entity", "vehicleExempt"}
CONFIG_TTL, ACTION_TTL = 900, 60


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
    if kind in ("warn", "kick", "ban", "freeze", "screenshot", "vehicleExempt"):
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
    elif kind == "protection":
        row = next((p for p in snap.get("protections", []) if p.get("id") == payload.id), None)
        fields = ("enabled", "profile", "action", "minConfidence", "screenshot", "discord")
        require(row and not row.get("locked") and set(payload.expected) == set(fields)
                and all(row.get(field) == payload.expected[field] for field in fields), 409,
                "That protection is unknown, locked, or changed. Refresh before editing.")
    elif kind == "cleanup":
        require(payload.scope == "client" or
                (snap.get("cleanup") or {}).get(payload.category) == payload.expected, 409,
                "Cleanup preview changed. Refresh before clearing entities.")
    elif kind == "inventory":
        db.ensure_schema()
        if payload.operation == "player":
            require(any(p.get("src") == payload.target and p.get("sessionKey") == payload.session
                        for p in snap.get("players", [])),
                    409, "That player's session changed. Refresh the player list.")
    elif kind == "stream":
        db.ensure_schema()
        if payload.operation == "start":
            require(any(p.get("src") == payload.target and p.get("sessionKey") == payload.session
                        for p in snap.get("players", [])),
                    409, "That player's session changed. Refresh before starting a stream.")
            require((snap.get("integrations") or {}).get("screenshots") == "started",
                    409, "Nexus-Screens is not running on this server.")

    rate("command:" + str(user["user_id"]), 60, 60)
    command_id = new_id()
    with db.transaction() as cur:
        timestamp = now()
        if kind == "stream":
            cur.execute("SELECT id FROM nx_servers WHERE id=%s FOR UPDATE", (server_id,))
            cur.execute("DELETE FROM nx_stream_viewers WHERE server=%s AND expires<=%s",
                        (server_id, timestamp))
            cur.execute("DELETE FROM nx_stream_frames WHERE server=%s AND updated<%s",
                        (server_id, timestamp - 20))
            cur.execute("SELECT actor,target,player_session FROM nx_stream_viewers "
                        "WHERE server=%s AND viewer=%s", (server_id, payload.viewerId))
            existing = cur.fetchone()
            if payload.operation == "start":
                require(not existing or
                        (str(existing["actor"]) == str(user["user_id"])
                         and existing["target"] == payload.target
                         and existing["player_session"] == payload.session),
                        409, "This stream tile belongs to a different watch session.")
                if not existing:
                    cur.execute("SELECT count(*) AS total FROM nx_stream_viewers "
                                "WHERE server=%s AND expires>%s", (server_id, timestamp))
                    require(int(cur.fetchone()["total"]) < 8, 409,
                            "This server already has the maximum of 8 live views.")
                    cur.execute("SELECT count(*) AS total FROM nx_stream_viewers "
                                "WHERE server=%s AND actor=%s AND expires>%s",
                                (server_id, user["user_id"], timestamp))
                    require(int(cur.fetchone()["total"]) < 4, 409,
                            "You can watch at most 4 players at once.")
                cur.execute(
                    """INSERT INTO nx_stream_viewers
                       (server,viewer,actor,target,player_session,expires)
                       VALUES(%s,%s,%s,%s,%s,%s)
                       ON CONFLICT(server,viewer) DO UPDATE SET expires=EXCLUDED.expires""",
                    # The first command may wait for the bridge's next sync.
                    # Once the page starts polling it renews this to 15 seconds.
                    (server_id, payload.viewerId, user["user_id"], payload.target,
                     payload.session, timestamp + 60),
                )
            else:
                require(existing and str(existing["actor"]) == str(user["user_id"]), 404,
                        "That live-view session is no longer yours.")
                cur.execute("DELETE FROM nx_stream_viewers WHERE server=%s AND viewer=%s",
                            (server_id, payload.viewerId))

        cur.execute(
            "INSERT INTO nx_commands(id,server,actor,actor_name,body,created,expires) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s)",
            (command_id, server_id, user["user_id"], user["name"],
             db.jsonb(payload.model_dump(mode="json")), timestamp,
             timestamp + (CONFIG_TTL if kind in CONFIG_KINDS else ACTION_TTL)),
        )
    audit(user, "command." + kind, str(server["name"]) + " / " + command_id)
    return reply({"id": command_id, "status": "pending"}, 202)


UUID = re.compile(r"^[0-9a-fA-F-]{36}$")


@router.get("/servers/{server_id}/inventory/{command_id}")
async def inventory_result(request: Request, server_id: str, command_id: str):
    """Poll for the answer to an inventory lookup this staff member queued.

    `pending`/`sent` while the game server has not answered yet; `ready` with
    the body once it has; the command's own status (failed, expired) otherwise.
    """
    user = authenticated(request)
    require("inventory" in PERMISSIONS.get(user["role"], ()), 403,
            "Your role cannot view inventories.")
    require(UUID.match(command_id), 404, "Unknown inventory request.")
    _server_of(user, server_id)
    db.ensure_schema()
    rate("inventory-view:" + str(user["user_id"]), 240, 60)
    command = db.one("SELECT actor, status, result FROM nx_commands WHERE id=%s AND server=%s",
                     (command_id, server_id))
    require(command and str(command["actor"]) == str(user["user_id"]), 404,
            "Unknown inventory request.")
    view = db.one("SELECT operation, ok, message, body, created FROM nx_inventory_views "
                  "WHERE server=%s AND command_id=%s", (server_id, command_id))
    if view:
        return reply({"status": "ready", "operation": view["operation"], "ok": view["ok"],
                      "message": view["message"], "body": view["body"], "at": view["created"],
                      "serverTime": now()})
    return reply({"status": command["status"], "result": command["result"], "serverTime": now()})


@router.post("/servers/{server_id}/streams/frames")
async def stream_frames(request: Request, server_id: str):
    origin_check(request)
    user = authenticated(request)
    require(user["role"] in ("owner", "administrator"), 403,
            "Only owners and administrators can view live player screens.")
    server = _server_of(user, server_id)
    require(_online(server["last_seen"]), 409, "Server is offline.")
    db.ensure_schema()
    # Batched requests can poll the full four-tile view at 4 Hz. This is a
    # dedicated limit and does not affect the dashboard's ordinary API budget.
    rate("stream-view:" + str(user["user_id"]), 270, 60)
    payload = StreamFramesRequest(**await json_body(request, 12_000))
    timestamp = now()
    snapshot = server.get("snapshot") or {}
    players = {int(player.get("src") or 0): player
               for player in snapshot.get("players", [])}
    frames = []
    with db.transaction() as cur:
        for viewer in payload.streams:
            cur.execute(
                """SELECT player_session,capture_session FROM nx_stream_viewers
                   WHERE server=%s AND viewer=%s AND actor=%s AND target=%s AND expires>%s""",
                (server_id, viewer.viewerId, user["user_id"], viewer.target, timestamp),
            )
            lease = cur.fetchone()
            player = players.get(viewer.target)
            if not lease or lease["player_session"] != viewer.session or not player or \
                    player.get("sessionKey") != viewer.session:
                if lease:
                    cur.execute("DELETE FROM nx_stream_viewers WHERE server=%s AND viewer=%s",
                                (server_id, viewer.viewerId))
                frames.append({"viewerId": viewer.viewerId, "active": False})
                continue

            cur.execute("UPDATE nx_stream_viewers SET expires=%s WHERE server=%s AND viewer=%s",
                        (timestamp + 15, server_id, viewer.viewerId))
            frame = None
            if lease["capture_session"]:
                cur.execute(
                    """SELECT frame_seq,
                              CASE WHEN frame_seq>%s THEN data ELSE NULL END AS data,
                              updated
                       FROM nx_stream_frames
                       WHERE server=%s AND target=%s AND updated>%s AND capture_session=%s""",
                    (viewer.afterSequence, server_id, viewer.target, timestamp - 10,
                     lease["capture_session"]),
                )
                frame = cur.fetchone()
            frames.append({
                "viewerId": viewer.viewerId, "active": True,
                "sequence": int(frame["frame_seq"]) if frame else 0,
                "updated": int(frame["updated"]) if frame else 0,
                "data": frame["data"] if frame else None,
            })
    return reply({"frames": frames})


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
