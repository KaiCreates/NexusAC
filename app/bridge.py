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

BEARER = re.compile(r"^Bearer ([A-Za-z0-9_-]{43})$")
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

        # One command per poll. Each carries an expected-value check that has to
        # see the result of the command before it, so they cannot be batched.
        cur.execute(
            """SELECT id, body, actor_name, expires FROM nx_commands
                WHERE server=%s AND status IN ('pending','sent') AND expires>%s
                ORDER BY created, id LIMIT 1""",
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
