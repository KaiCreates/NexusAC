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
import re

from fastapi import Request

from . import db
from .protocol import MAX_MEDIA_BYTES, MAX_SNAPSHOT_BYTES, MediaRequest, SyncRequest
from .security import HttpError, rate, reply, require, sha256, now

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


def server_for(request: Request) -> dict:
    match = BEARER.match(request.headers.get("authorization", "") or "")
    require(match, 401, "A server API key is required.")
    server = db.one("SELECT * FROM nx_servers WHERE token_hash=%s", (sha256(match.group(1)),))
    require(server, 401, "Invalid or revoked server API key.")
    rate(f"bridge:{server['id']}", 100, 60)
    return server  # type: ignore[return-value]


async def handle(request: Request, action: str):
    require(request.method == "POST", 405, "POST required.")
    server = server_for(request)
    server_id = str(server["id"])

    if action == "ping":
        return reply({
            "protocol": 1,
            "ok": True,
            "serverId": server_id,
            "serverName": server["name"],
            "serverTime": now(),
        })
    if action == "media":
        return await _media(request, server_id)
    require(action == "sync", 404, "Unknown bridge endpoint.")
    return await _sync(request, server, server_id)


async def _media(request: Request, server_id: str):
    payload = MediaRequest(**await json_body(request, MAX_MEDIA_BYTES + 50_000))
    try:
        raw = base64.b64decode(payload.data.split(",", 1)[1], validate=True)
    except (binascii.Error, IndexError):
        raise HttpError(400, "Screenshot is not valid base64.")
    require(len(raw) > 3 and raw[:3] == b"\xff\xd8\xff", 400, "Expected a JPEG screenshot.")
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
    return reply({"ok": True})


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


EVENT_RETENTION_DAYS = 30
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


async def _sync(request: Request, server: dict, server_id: str):
    body = await json_body(request, MAX_SNAPSHOT_BYTES)
    payload = SyncRequest(**body)
    require(
        abs(now() - payload.sentAt) <= CLOCK_SKEW_SECONDS,
        400,
        "Server clock differs from the website by more than 90 seconds.",
    )

    snapshot = payload.snapshot.model_dump(mode="json")
    evidence = snapshot.pop("evidence", [])
    # Identities are mirrored into their own tables, not kept in the snapshot
    # blob -- the blob is replaced wholesale on every poll and this data has to
    # accumulate.
    identities = snapshot.pop("identities", None) or {}
    event_log = snapshot.pop("eventLog", None) or {}
    punishments = snapshot.pop("punishments", None) or {}

    with db.transaction() as cur:
        # Re-read inside the write transaction: a key rotation and a poll that
        # started before it cannot race past each other.
        cur.execute(
            "SELECT boot, sequence FROM nx_servers WHERE id=%s AND token_hash=%s FOR UPDATE",
            (server_id, server["token_hash"]),
        )
        current = cur.fetchone()
        require(current, 401, "Server API key was rotated.")

        if current["boot"] == payload.boot:
            require(
                payload.sequence > int(current["sequence"]),
                409,
                "Duplicate or out-of-order snapshot.",
            )
        else:
            cur.execute(
                "SELECT boot FROM nx_bridge_boots WHERE server=%s AND boot=%s",
                (server_id, payload.boot),
            )
            require(cur.fetchone() is None, 409, "This resource session has already ended.")
            cur.execute(
                "INSERT INTO nx_bridge_boots VALUES(%s,%s,%s)", (server_id, payload.boot, now())
            )

        cur.execute(
            "UPDATE nx_servers SET last_seen=%s, snapshot=%s, boot=%s, sequence=%s WHERE id=%s",
            (now(), db.jsonb(snapshot), payload.boot, payload.sequence, server_id),
        )

        for item in evidence:
            cur.execute(
                """INSERT INTO nx_evidence VALUES(%s,%s,%s,%s)
                   ON CONFLICT(server,id) DO UPDATE SET body=EXCLUDED.body, updated=EXCLUDED.updated""",
                (server_id, item["id"], db.jsonb(item), now()),
            )

        identity_cursor = _store_identities(cur, server, server_id, identities)
        event_cursor = _store_events(cur, server, server_id, event_log, payload.sequence)
        punish_cursor = _store_punishments(cur, server, server_id, punishments)

        for ack in payload.acknowledgements:
            status = "uncertain" if ack.uncertain else ("succeeded" if ack.ok else "failed")
            cur.execute(
                """UPDATE nx_commands SET status=%s, result=%s, ack_at=%s
                    WHERE id=%s AND server=%s AND status IN ('sent','expired')""",
                (status, ack.message, now(), ack.id, server_id),
            )

        cur.execute(
            """UPDATE nx_commands
                  SET status='expired',
                      result='No acknowledgement before expiry; a sent action may still have executed.'
                WHERE server=%s AND expires<=%s AND status IN ('pending','sent')""",
            (server_id, now()),
        )

        # Dispatch a small batch per poll. Each command still carries an
        # expected-value check, so stale edits are refused while several toggles
        # can reach the server in the same near-real-time sync.
        cur.execute(
            """SELECT id, body, actor_name, expires FROM nx_commands
                WHERE server=%s AND status IN ('pending','sent') AND expires>%s
                ORDER BY created, id LIMIT 10""",
            (server_id, now()),
        )
        queued = cur.fetchall()
        for item in queued:
            cur.execute("UPDATE nx_commands SET status='sent' WHERE id=%s", (item["id"],))

    return reply(
        {
            "protocol": 1,
            "serverTime": now(),
            "accepted": payload.sequence,
            # Where the identity mirror has got to. The resource resumes from
            # this, so a batch that never landed is simply sent again.
            "identityCursor": identity_cursor,
            "eventCursor": event_cursor,
            "punishCursor": punish_cursor,
            "commands": [
                {
                    "id": str(item["id"]),
                    "actor": item["actor_name"],
                    "expires": int(item["expires"]),
                    **item["body"],
                }
                for item in queued
            ],
        }
    )
