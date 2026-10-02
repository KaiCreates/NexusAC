"""The endpoint pair the anti-cheat calls: /api/control/bridge/sync and .../media.

Authenticated by the server's 43-character API key, never by a cookie. The whole
sync is one database transaction because boot registration, the sequence advance
and command dispatch have to agree: two overlapping polls must not be able to
hand the same command out twice.
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import re

from fastapi import Request

from . import db, hub
from .protocol import (
    MAX_MEDIA_BYTES, MAX_SNAPSHOT_BYTES, MAX_STREAM_FRAME_BYTES,
    MediaRequest, StreamFrameRequest, StreamStartRequest, SyncRequest,
)
from .security import HttpError, rate, reply, require, sha256, now

log = logging.getLogger("nexusac.bridge")

BEARER = re.compile(r"^Bearer\s+([A-Za-z0-9_-]{43})$", re.IGNORECASE)
CLOCK_SKEW_SECONDS = 90


async def json_body(request: Request, maximum: int) -> dict:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > maximum:
        raise HttpError(413, "Request is too large.")
    size, chunks = 0, []
    async for chunk in request.stream():
        size += len(chunk)
        if size > maximum:
            raise HttpError(413, "Request is too large.")
        chunks.append(chunk)
    try:
        return json.loads(b"".join(chunks).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise HttpError(400, "Invalid JSON.")


BRIDGE_LIMITS = {
    "ping": 30, "heartbeat": 30, "wait": 180, "sync": 60,
    "media": 180, "stream-start": 60, "stream": 600, "inventory": 60,
}


def server_for(request: Request, action: str) -> dict:
    match = BEARER.match(request.headers.get("authorization", "") or "")
    require(match, 401, "A server API key is required.")
    # Cached in memory (app/hub.py). This used to be SELECT *, which pulled the
    # whole ~300 KB snapshot out of the database on every bridge request.
    state = hub.by_token(sha256(match.group(1)))
    require(state, 401, "Invalid or revoked server API key.")
    server = state.row
    # Media uploads are bursty. Sharing their bucket with sync/heartbeat made
    # an evidence burst mark an otherwise healthy server offline (429 loop).
    rate(f"bridge:{server['id']}:{action}", BRIDGE_LIMITS[action], 60)
    return server  # type: ignore[return-value]


async def handle(request: Request, action: str):
    require(request.method == "POST", 405, "POST required.")
    require(action in BRIDGE_LIMITS, 404, "Unknown bridge endpoint.")
    server = server_for(request, action)
    server_id = str(server["id"])

    if action == "ping":
        return reply({
            "protocol": 1,
            "ok": True,
            "serverId": server_id,
            "serverName": server["name"],
            "serverTime": now(),
        })
    if action == "heartbeat":
        # Lightweight recovery path used when a full snapshot cannot be
        # accepted. Liveness only, kept in memory (app/hub.py).
        server["last_seen"] = now()
        return reply({"protocol": 1, "ok": True, "serverTime": now(), "degraded": True})
    if action == "wait":
        # A long poll: held until a staff member queues a command (answered in
        # well under a second) or LONG_POLL_SECONDS pass. Waiting costs no
        # database access at all. `held` tells the resource to re-poll at once.
        commands = await hub.long_poll(hub.by_id(server_id))
        return reply({"protocol": 1, "serverTime": now(), "held": True, "commands": commands})
    if action == "media":
        return await _media(request, server_id)
    if action == "inventory":
        return await _inventory(request, server_id)
    if action == "stream-start":
        return await _stream_start(request, server, server_id)
    if action == "stream":
        return await _stream(request, server, server_id)
    require(action == "sync", 404, "Unknown bridge endpoint.")
    try:
        return await _sync(request, server, server_id)
    except HttpError:
        raise
    except Exception as error:
        # Keep bridge failures machine-readable. Some reverse proxies replace a
        # framework 503 body with an empty HTML response, which hides the actual
        # schema/database problem from the FiveM console.
        log.exception("[NexusAC bridge] %s failed: %s", action, error)
        return reply({
            "error": "Bridge sync could not be stored.",
            "code": type(error).__name__,
        }, 503)


async def _media(request: Request, server_id: str):
    payload = MediaRequest(**await json_body(request, MAX_MEDIA_BYTES + 50_000))
    try:
        raw = base64.b64decode(payload.data.split(",", 1)[1], validate=True)
    except (binascii.Error, IndexError):
        raise HttpError(400, "Screenshot is not valid base64.")
    require(len(raw) > 3 and raw[:3] == b"\xff\xd8\xff", 400, "Expected a JPEG screenshot.")
    state = hub.by_id(server_id)
    if state and payload.evidenceId in state.evidence:
        hub.flush(state)   # the case is still buffered; it must exist before its image
    require(
        db.one(
            "SELECT id FROM nx_evidence WHERE server=%s AND id=%s", (server_id, payload.evidenceId)
        ),
        409,
        "Evidence metadata must arrive before its screenshot.",
    )
    db.execute(
        """INSERT INTO nx_media VALUES(%s,%s,%s,%s,%s)
           ON CONFLICT(server,evidence_id,slot) DO UPDATE SET data=EXCLUDED.data, created=EXCLUDED.created""",
        (server_id, payload.evidenceId, payload.slot, payload.data, now()),
    )
    if state:
        state.evidence_version += 1   # the dashboard's image counts change
    return reply({"ok": True})


def _player_session_matches(server: dict, target: int, player_session: str) -> bool:
    state = hub.by_id(server["id"])
    snapshot = hub.snapshot_of(state) if state else {}
    return any(int(player.get("src") or 0) == target
               and player.get("sessionKey") == player_session
               for player in snapshot.get("players", []))


async def _inventory(request: Request, server_id: str):
    """Store the game server's answer to one staff inventory lookup.

    Only accepted for an `inventory` command this website queued for this
    server, so the endpoint cannot be used as general storage. Results are a
    short-lived cache: anything older than ten minutes is pruned here.
    """
    from .protocol import MAX_INVENTORY_BYTES, InventoryUpload

    payload = InventoryUpload(**await json_body(request, MAX_INVENTORY_BYTES + 8192))
    db.ensure_schema()
    timestamp = now()
    with db.transaction() as cur:
        cur.execute("SELECT body FROM nx_commands WHERE id=%s AND server=%s",
                    (payload.commandId, server_id))
        row = cur.fetchone()
        require(row and (row["body"] or {}).get("type") == "inventory", 404,
                "No inventory request with that id.")
        cur.execute("DELETE FROM nx_inventory_views WHERE server=%s AND created<%s",
                    (server_id, timestamp - 600))
        cur.execute(
            """INSERT INTO nx_inventory_views(server,command_id,operation,ok,message,body,created)
               VALUES(%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT(server,command_id) DO UPDATE SET
                 operation=EXCLUDED.operation, ok=EXCLUDED.ok, message=EXCLUDED.message,
                 body=EXCLUDED.body, created=EXCLUDED.created""",
            (server_id, payload.commandId, payload.operation, payload.ok, payload.message,
             db.jsonb(payload.body), timestamp),
        )
    return reply({"ok": True})


async def _stream_start(request: Request, server: dict, server_id: str):
    from .protocol import StreamStartRequest

    payload = StreamStartRequest(**await json_body(request, 4096))
    if not _player_session_matches(server, payload.target, payload.playerSession):
        return reply({"ok": True, "active": False})
    db.ensure_schema()
    timestamp = now()
    with db.transaction() as cur:
        cur.execute(
            """UPDATE nx_stream_viewers SET capture_session=%s
               WHERE server=%s AND target=%s AND player_session=%s AND expires>%s""",
            (payload.captureSession, server_id, payload.target, payload.playerSession,
             timestamp),
        )
        cur.execute(
            """SELECT 1 FROM nx_stream_viewers
               WHERE server=%s AND target=%s AND player_session=%s AND expires>%s
                 AND capture_session=%s LIMIT 1""",
            (server_id, payload.target, payload.playerSession, timestamp, payload.captureSession),
        )
        active = cur.fetchone() is not None
    return reply({"ok": True, "active": active})


async def _stream(request: Request, server: dict, server_id: str):
    from .protocol import StreamFrameRequest

    payload = StreamFrameRequest(**await json_body(request, MAX_STREAM_FRAME_BYTES + 8192))
    try:
        encoded = payload.data.split(",", 1)[1]
        image = base64.b64decode(encoded, validate=True)
    except (binascii.Error, IndexError):
        raise HttpError(400, "Stream frame is not valid base64.")
    is_jpeg = payload.data.startswith("data:image/jpeg;") and image.startswith(b"\xff\xd8\xff")
    is_webp = (payload.data.startswith("data:image/webp;") and len(image) >= 12
               and image[:4] == b"RIFF" and image[8:12] == b"WEBP")
    require(is_jpeg or is_webp, 400, "Stream frame is not a valid JPEG or WebP image.")
    if not _player_session_matches(server, payload.target, payload.playerSession):
        return reply({"ok": True, "active": False})

    db.ensure_schema()
    timestamp = now()
    with db.transaction() as cur:
        cur.execute(
            """UPDATE nx_stream_viewers SET capture_session=%s
               WHERE server=%s AND target=%s AND player_session=%s AND expires>%s
                 AND capture_session IS NULL""",
            (payload.captureSession, server_id, payload.target, payload.playerSession, timestamp),
        )
        cur.execute(
            """SELECT 1 FROM nx_stream_viewers
               WHERE server=%s AND target=%s AND player_session=%s AND capture_session=%s
                 AND expires>%s LIMIT 1""",
            (server_id, payload.target, payload.playerSession, payload.captureSession, timestamp),
        )
        if cur.fetchone() is None:
            cur.execute("DELETE FROM nx_stream_frames "
                        "WHERE server=%s AND target=%s AND capture_session=%s",
                        (server_id, payload.target, payload.captureSession))
            return reply({"ok": True, "active": False})

        cur.execute(
            """INSERT INTO nx_stream_frames(server,target,capture_session,frame_seq,data,updated)
               VALUES(%s,%s,%s,%s,%s,%s)
               ON CONFLICT(server,target) DO UPDATE SET
                 capture_session=EXCLUDED.capture_session, frame_seq=EXCLUDED.frame_seq,
                 data=EXCLUDED.data, updated=EXCLUDED.updated
               WHERE (nx_stream_frames.capture_session=EXCLUDED.capture_session
                      AND EXCLUDED.frame_seq>nx_stream_frames.frame_seq)
                  OR nx_stream_frames.capture_session<>EXCLUDED.capture_session""",
            (server_id, payload.target, payload.captureSession, payload.sequence,
             payload.data, timestamp),
        )
    return reply({"ok": True, "active": True})


def _store_identities(cur, server: dict, server_id: str, block: dict) -> int:
    """Merge one batch of mirrored identities in, and return the cursor now held.

    Idempotent on purpose. The resource resends a batch whenever a sync fails or
    an acknowledgement is lost, so every write here has to be safe to repeat.
    That is why counters are merged with GREATEST rather than added: adding would
    inflate on every retry, and `sessions` is only ever "the most any one server
    has seen for this identity", which is honest and stable.
    """
    held = int(server.get("identity_cursor") or 0)
    rows = block.get("rows") or []
    if not rows:
        return held

    workspace = server["workspace"]

    cur.executemany(
        """INSERT INTO nx_identities
               (workspace, uid, first_seen, last_seen, sessions, last_name,
                banned, ban_reason, banned_at, last_server)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (workspace, uid) DO UPDATE SET
               first_seen  = LEAST(nx_identities.first_seen, EXCLUDED.first_seen),
               last_seen   = GREATEST(nx_identities.last_seen, EXCLUDED.last_seen),
               sessions    = GREATEST(nx_identities.sessions, EXCLUDED.sessions),
               -- Only the more recent sighting gets to rename or re-flag.
               last_name   = CASE WHEN EXCLUDED.last_seen >= nx_identities.last_seen
                                  THEN EXCLUDED.last_name ELSE nx_identities.last_name END,
               banned      = CASE WHEN EXCLUDED.last_seen >= nx_identities.last_seen
                                  THEN EXCLUDED.banned ELSE nx_identities.banned END,
               ban_reason  = CASE WHEN EXCLUDED.last_seen >= nx_identities.last_seen
                                  THEN EXCLUDED.ban_reason ELSE nx_identities.ban_reason END,
               banned_at   = COALESCE(EXCLUDED.banned_at, nx_identities.banned_at),
               last_server = EXCLUDED.last_server""",
        [
            (
                workspace, row["uid"], row["first"], row["last"], row["sessions"],
                row["name"][:100], row["banned"], row["reason"], row["bannedAt"], server_id,
            )
            for row in rows
        ],
    )

    marks = [
        (workspace, row["uid"], mark["kind"], mark["value"],
         mark["first"] or row["first"], mark["last"] or row["last"], mark["seen"])
        for row in rows
        for mark in (row.get("marks") or [])
    ]
    if marks:
        cur.executemany(
            """INSERT INTO nx_identity_marks
                   (workspace, uid, kind, value, first_seen, last_seen, times_seen)
               VALUES (%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (workspace, uid, kind, value) DO UPDATE SET
                   first_seen = LEAST(nx_identity_marks.first_seen, EXCLUDED.first_seen),
                   last_seen  = GREATEST(nx_identity_marks.last_seen, EXCLUDED.last_seen),
                   times_seen = GREATEST(nx_identity_marks.times_seen, EXCLUDED.times_seen)""",
            marks,
        )

    # The cursor only moves forward, so a batch that arrives out of order after a
    # retry cannot rewind the mirror and cause the same rows to be sent forever.
    cursor = max(held, int(block.get("cursor") or 0))
    if cursor != held:
        cur.execute(
            "UPDATE nx_servers SET identity_cursor=%s WHERE id=%s", (cursor, server_id)
        )
    return cursor


# 7 days, not 30: on a 0.5 GB database a busy server's event log was the
# biggest table after screenshots. app/maintenance.py trims harder if needed.
EVENT_RETENTION_DAYS = int(os.environ.get("EVENT_RETENTION_DAYS", "7"))
# One sweep every N syncs. At a ~3 second poll that is roughly hourly, which is
# often enough for a 30-day window and rare enough not to sit in the hot path.
EVENT_SWEEP_EVERY = 1200


def _store_events(cur, server: dict, server_id: str, block: dict, sequence: int) -> int:
    """Append one batch of raw events, and return the cursor now held.

    Deduplicated on (server, boot, seq), so a resent batch inserts nothing. The
    cursor resets when the boot changes, because the resource's sequence starts
    again at zero on every resource start -- comparing across boots would make a
    fresh session look like a replay and drop all of it.
    """
    boot = block.get("boot")
    rows = block.get("rows") or []
    held = int(server.get("event_cursor") or 0)
    same_boot = boot is not None and server.get("event_boot") == boot

    if not rows:
        return held if same_boot else 0

    workspace = server["workspace"]
    cur.executemany(
        """INSERT INTO nx_events
               (workspace, server, boot, seq, at, type,
                sender, sender_name, target, target_name, data)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (server, boot, seq) DO NOTHING""",
        [
            (
                workspace, server_id, boot, row["seq"], row["at"], row["type"],
                row["sender"], row["senderName"], row["target"], row["targetName"],
                db.jsonb(row.get("data") or {}),
            )
            for row in rows
        ],
    )

    cursor = int(block.get("cursor") or 0)
    if same_boot:
        cursor = max(held, cursor)
    cur.execute(
        "UPDATE nx_servers SET event_boot=%s, event_cursor=%s WHERE id=%s",
        (boot, cursor, server_id),
    )

    # Retention. Without this the table is unbounded, and an event log is the
    # one table on this site that genuinely would grow without limit.
    if sequence % EVENT_SWEEP_EVERY == 0:
        cur.execute(
            "DELETE FROM nx_events WHERE server=%s AND at < %s",
            (server_id, now() - EVENT_RETENTION_DAYS * 86400),
        )

    return cursor


def _store_punishments(cur, server: dict, server_id: str, block: dict) -> int:
    """Append punishments. Same boot/seq dedup as events, and no retention sweep
    -- this is the table somebody appeals against a year later."""
    boot = block.get("boot")
    rows = block.get("rows") or []
    held = int(server.get("punish_cursor") or 0)
    same_boot = boot is not None and server.get("punish_boot") == boot

    if not rows:
        return held if same_boot else 0

    cur.executemany(
        """INSERT INTO nx_punishments
               (workspace, server, boot, seq, at, kind, identifier, name,
                reason, by_actor, auto, days, detector, evidence)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (server, boot, seq) DO NOTHING""",
        [
            (
                server["workspace"], server_id, boot, row["seq"], row["at"], row["kind"],
                row["identifier"], row["name"], row["reason"], row["by"],
                row["auto"], row["days"], row["detector"], row["evidence"],
            )
            for row in rows
        ],
    )

    cursor = int(block.get("cursor") or 0)
    if same_boot:
        cursor = max(held, cursor)
    cur.execute(
        "UPDATE nx_servers SET punish_boot=%s, punish_cursor=%s WHERE id=%s",
        (boot, cursor, server_id),
    )
    return cursor


def _optional(cur, degraded: list[str], label: str, fn, *args) -> int:
    """Run one mirror inside a savepoint; never let it fail the sync.

    psycopg opens a real SAVEPOINT for a nested transaction block, so an error
    here rolls back only this mirror. Without that, Postgres marks the whole
    transaction aborted and every statement after it fails too -- including the
    command dispatch, which is the part that actually has to work.
    """
    try:
        with cur.connection.transaction():
            return fn(cur, *args)
    except Exception as error:  # noqa: BLE001 - deliberately broad, see above
        degraded.append(label)
        log.warning(
            "[NexusAC bridge] %s mirror skipped for server %s: %s: %s. "
            "Run scripts/migrate.py if this is a missing table or column.",
            label, args[1] if len(args) > 1 else "?", type(error).__name__, error,
        )
        return 0


async def _sync(request: Request, server: dict, server_id: str):
    body = await json_body(request, MAX_SNAPSHOT_BYTES)
    payload = SyncRequest(**body)
    require(
        abs(now() - payload.sentAt) <= CLOCK_SKEW_SECONDS,
        400,
        "Server clock differs from the website by more than 90 seconds.",
    )

    # A freshly deployed site may receive its first event batch before any UI
    # request has triggered schema setup. Ensure migrations here, at the actual
    # ingestion boundary, so the first batch is stored instead of being marked
    # degraded and left invisible until somebody opens /events.
    db.ensure_schema()

    snapshot = payload.snapshot.model_dump(mode="json")
    evidence = snapshot.pop("evidence", [])
    # Identities are mirrored into their own tables, not kept in the snapshot
    # blob -- the blob is replaced wholesale on every poll and this data has to
    # accumulate.
    identities = snapshot.pop("identities", None) or {}
    event_log = snapshot.pop("eventLog", None) or {}
    punishments = snapshot.pop("punishments", None) or {}

    # Buffered in memory and written in batches (app/hub.py); acknowledgements
    # and command redelivery still go to the database straight away.
    return reply(hub.accept_sync(hub.by_id(server_id), payload, snapshot, evidence,
                                 identities, event_log, punishments))
