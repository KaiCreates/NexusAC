"""Live game-server state in memory, written to Postgres in batches.

Why this exists: Neon's free plan stops billing compute only after 5 minutes
with no database activity, and suspends the database once 100 CU-hours are used
in a month. The game server talks to this site every few seconds, so when every
bridge request touched the database it never slept (~180 CU-hours a month), and
every request also read the ~300 KB snapshot back out (~75 GB of transfer a
month against a 5 GB allowance).

So the hot path never touches the database:
  * the API key -> server lookup is cached (never the snapshot column),
  * the live snapshot, last-seen and sequence live here,
  * evidence and the identity/event/punishment mirrors are buffered here,
  * the command channel is a long poll answered from memory the moment a staff
    member queues something (config and actions reach the game server in well
    under a second).
Everything buffered is written in one transaction every FLUSH_SECONDS (default
20 minutes), when a page needs it from the database, when a buffer grows large,
and on shutdown. Things staff do (commands, acknowledgements, new resource
boots, screenshots) are written straight away -- they are rare and someone is
waiting on them.

Single process only: this assumes one uvicorn worker (the Render start command).
If the website process is killed without a clean shutdown, up to FLUSH_SECONDS
of website-side history (events, identities, the latest snapshot) is lost; bans
and evidence also live on the game server, which resends what was not stored.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
import uuid
from typing import Any

from . import db, maintenance
from .security import HttpError, now, require

log = logging.getLogger("nexusac.hub")

FLUSH_SECONDS = max(60, int(os.environ.get("FLUSH_SECONDS", "1200")))
LONG_POLL_SECONDS = 25
MAX_BUFFERED_EVENTS = 4000       # flush early past these
MAX_BUFFERED_EVIDENCE = 150
MAX_BUFFERED_IDENTITIES = 2000
INSTANCE = uuid.uuid4().hex[:8]  # versions change on restart, so pages reload

SERVER_COLUMNS = ("id, workspace, name, token_hash, token_hint, created, last_seen, boot, sequence, "
                  "identity_cursor, event_cursor, event_boot, punish_cursor, punish_boot")
CURSOR_FIELDS = ("identity_cursor", "event_cursor", "event_boot", "punish_cursor", "punish_boot")

_lock = threading.RLock()
_by_id: dict[str, "ServerState"] = {}
_by_token: dict[str, str] = {}
_bad_tokens: dict[str, float] = {}


class ServerState:
    def __init__(self, row: dict):
        self.row = dict(row)                 # live view, cursors included
        self.row["id"] = str(row["id"])
        self.row["workspace"] = str(row["workspace"])
        self.db_cursors = {k: row.get(k) for k in CURSOR_FIELDS}   # what the database holds
        self.snapshot: dict | None = None
        self.snapshot_loaded = False
        self.version = 0
        self.dirty = False
        self.evidence: dict[str, dict] = {}
        self.identity_rows: list[dict] = []
        self.identity_cursor_target = int(row.get("identity_cursor") or 0)
        self.event_blocks: list[dict] = []   # {"boot", "rows", "cursor", "sequence"}
        self.punish_blocks: list[dict] = []
        self.evidence_version = 0
        self.commands_version = 0
        self.pending_dispatch = True         # unknown after a restart -> check once
        self.open_commands = True            # sent but not yet acknowledged
        self.degraded: list[str] = []
        self.last_flush = time.time()
        self.wake: asyncio.Event | None = None

    @property
    def id(self) -> str:
        return self.row["id"]

    def buffered(self) -> bool:
        return bool(self.dirty or self.evidence or self.identity_rows or self.event_blocks or self.punish_blocks)

    def event(self) -> asyncio.Event:
        if self.wake is None:
            self.wake = asyncio.Event()
        return self.wake


# --------------------------------------------------------------------- lookups

def _load(where: str, arg: Any) -> ServerState | None:
    row = db.one("SELECT %s FROM nx_servers WHERE %s=%%s" % (SERVER_COLUMNS, where), (arg,))
    if not row:
        return None
    state = ServerState(row)
    with _lock:
        existing = _by_id.get(state.id)
        if existing:
            return existing
        _by_id[state.id] = state
        _by_token[row["token_hash"]] = state.id
    return state


def by_token(token_hash: str) -> ServerState | None:
    with _lock:
        server_id = _by_token.get(token_hash)
        if server_id and server_id in _by_id:
            return _by_id[server_id]
        if _bad_tokens.get(token_hash, 0) > time.time():
            return None
    state = _load("token_hash", token_hash)
    if not state:
        with _lock:
            _bad_tokens[token_hash] = time.time() + 60   # a wrong key cannot keep the database awake
    return state


def by_id(server_id: str, workspace: str | None = None) -> ServerState | None:
    with _lock:
        state = _by_id.get(str(server_id))
    if not state:
        try:
            uuid.UUID(str(server_id))
        except ValueError:
            return None
        state = _load("id", str(server_id))
    if state and workspace is not None and state.row["workspace"] != str(workspace):
        return None
    return state


def forget(server_id: str, flush_first: bool = True) -> None:
    """Drop a server from memory (key rotated, server deleted)."""
    with _lock:
        state = _by_id.get(str(server_id))
    if state and flush_first:
        try:
            flush(state)
        except Exception as error:  # noqa: BLE001
            log.warning("[NexusAC hub] flush before forget failed: %s", error)
    with _lock:
        _by_id.pop(str(server_id), None)
        for token, sid in list(_by_token.items()):
            if sid == str(server_id):
                del _by_token[token]


def last_seen(server_id: str, fallback: Any = None) -> Any:
    with _lock:
        state = _by_id.get(str(server_id))
    if state and state.row.get("last_seen") is not None:
        return state.row["last_seen"]
    return fallback


def snapshot_of(state: ServerState) -> dict:
    if not state.snapshot_loaded:
        row = db.one("SELECT snapshot FROM nx_servers WHERE id=%s", (state.id,))
        if state.snapshot is None:
            state.snapshot = (row or {}).get("snapshot") or {}
        state.snapshot_loaded = True
    return state.snapshot or {}


def states_in(workspace: str) -> list[ServerState]:
    with _lock:
        return [s for s in _by_id.values() if s.row["workspace"] == str(workspace)]


# --------------------------------------------------------------------- sync

def _mirror_cursor(held: int, held_boot: Any, boot: Any, rows: list, cursor: Any) -> tuple[int, Any]:
    """Same rule as bridge._store_events/_store_punishments, without the database."""
    same_boot = boot is not None and held_boot == boot
    if not rows:
        return (held if same_boot else 0), (held_boot if same_boot else held_boot)
    value = int(cursor or 0)
    if same_boot:
        value = max(held, value)
    return value, boot


def accept_sync(state: ServerState, payload, snapshot: dict, evidence: list, identities: dict,
                event_log: dict, punishments: dict) -> dict:
    row = state.row
    if row.get("boot") == payload.boot:
        require(payload.sequence > int(row.get("sequence") or 0), 409, "Duplicate or out-of-order snapshot.")
    else:
        # A new resource session: rare, recorded straight away.
        with db.transaction() as cur:
            cur.execute("SELECT boot FROM nx_bridge_boots WHERE server=%s AND boot=%s", (state.id, payload.boot))
            require(cur.fetchone() is None, 409, "This resource session has already ended.")
            cur.execute("INSERT INTO nx_bridge_boots VALUES(%s,%s,%s)", (state.id, payload.boot, now()))
            cur.execute("UPDATE nx_servers SET boot=%s, sequence=%s, last_seen=%s WHERE id=%s",
                        (payload.boot, payload.sequence, now(), state.id))
    row["boot"], row["sequence"], row["last_seen"] = payload.boot, payload.sequence, now()
    state.snapshot, state.snapshot_loaded = snapshot, True
    state.version += 1
    state.dirty = True

    if evidence:
        for item in evidence:
            state.evidence[str(item["id"])] = item
        state.evidence_version += 1

    # Identities: the cursor only moves forward (bridge._store_identities).
    id_rows = identities.get("rows") or []
    if id_rows:
        state.identity_rows.extend(id_rows)
        row["identity_cursor"] = max(int(row.get("identity_cursor") or 0), int(identities.get("cursor") or 0))
    identity_cursor = int(row.get("identity_cursor") or 0)

    ev_rows = event_log.get("rows") or []
    event_cursor, event_boot = _mirror_cursor(int(row.get("event_cursor") or 0), row.get("event_boot"),
                                              event_log.get("boot"), ev_rows, event_log.get("cursor"))
    if ev_rows:
        state.event_blocks.append({"boot": event_log.get("boot"), "rows": ev_rows,
                                   "cursor": event_log.get("cursor"), "sequence": payload.sequence})
        row["event_cursor"], row["event_boot"] = event_cursor, event_boot

    pn_rows = punishments.get("rows") or []
    punish_cursor, punish_boot = _mirror_cursor(int(row.get("punish_cursor") or 0), row.get("punish_boot"),
                                                punishments.get("boot"), pn_rows, punishments.get("cursor"))
    if pn_rows:
        state.punish_blocks.append({"boot": punishments.get("boot"), "rows": pn_rows,
                                    "cursor": punishments.get("cursor")})
        row["punish_cursor"], row["punish_boot"] = punish_cursor, punish_boot

    # Staff are waiting on these: acknowledgements and redelivery go to the
    # database now, but only while there is something open.
    commands: list[dict] = []
    if payload.acknowledgements or state.open_commands:
        commands = _acknowledge_and_redeliver(state, payload.acknowledgements)

    events_buffered = sum(len(b["rows"]) for b in state.event_blocks)
    if (events_buffered > MAX_BUFFERED_EVENTS or len(state.evidence) > MAX_BUFFERED_EVIDENCE
            or len(state.identity_rows) > MAX_BUFFERED_IDENTITIES):
        flush(state)

    degraded, state.degraded = state.degraded, []
    return {
        "protocol": 1,
        "serverTime": now(),
        "accepted": payload.sequence,
        "identityCursor": identity_cursor,
        "eventCursor": event_cursor,
        "punishCursor": punish_cursor,
        "degraded": degraded,
        "commands": commands,
    }


def _command_json(item: dict) -> dict:
    return {"id": str(item["id"]), "actor": item["actor_name"], "expires": int(item["expires"]), **item["body"]}


def _acknowledge_and_redeliver(state: ServerState, acknowledgements) -> list[dict]:
    with db.transaction() as cur:
        for ack in acknowledgements:
            status = "uncertain" if ack.uncertain else ("succeeded" if ack.ok else "failed")
            cur.execute(
                """UPDATE nx_commands SET status=%s, result=%s, ack_at=%s
                    WHERE id=%s AND server=%s AND status IN ('sent','expired') RETURNING body""",
                (status, ack.message, now(), ack.id, state.id),
            )
            command = (cur.fetchone() or {}).get("body") or {}
            if (command.get("type") == "stream" and command.get("operation") == "start"
                    and not ack.ok and not ack.uncertain):
                cur.execute("DELETE FROM nx_stream_viewers WHERE server=%s AND viewer=%s",
                            (state.id, command.get("viewerId")))
        cur.execute(
            """UPDATE nx_commands SET status='expired',
                      result='No acknowledgement before expiry; a sent action may still have executed.'
                WHERE server=%s AND expires<=%s AND status IN ('pending','sent')""",
            (state.id, now()),
        )
        cur.execute(
            """SELECT id, body, actor_name, expires FROM nx_commands
                WHERE server=%s AND status IN ('pending','sent') AND expires>%s
                ORDER BY created, id LIMIT 10""",
            (state.id, now()),
        )
        queued = cur.fetchall()
        for item in queued:
            cur.execute("UPDATE nx_commands SET status='sent' WHERE id=%s", (item["id"],))
    state.open_commands = bool(queued)
    if acknowledgements or queued:
        state.commands_version += 1
    return [_command_json(item) for item in queued]


# --------------------------------------------------------------------- commands

def command_queued(server_id: str) -> None:
    """Called after a staff command is inserted: wake the held long poll."""
    state = by_id(server_id)
    if not state:
        return
    state.pending_dispatch = True
    state.open_commands = True
    state.commands_version += 1
    if state.wake is not None:
        state.wake.set()


def _dispatch_pending(state: ServerState) -> list[dict]:
    with db.transaction() as cur:
        cur.execute(
            """SELECT id, body, actor_name, expires FROM nx_commands
               WHERE server=%s AND status='pending' AND expires>%s
               ORDER BY created, id LIMIT 10""", (state.id, now()),
        )
        queued = cur.fetchall()
        for item in queued:
            cur.execute("UPDATE nx_commands SET status='sent' WHERE id=%s", (item["id"],))
    if queued:
        state.open_commands = True
        state.commands_version += 1
    return [_command_json(item) for item in queued]


async def long_poll(state: ServerState, seconds: float = LONG_POLL_SECONDS) -> list[dict]:
    """Hold the game server's request until a command is queued (or `seconds`
    pass). Answered from memory; the database is only read when there is
    something to hand out."""
    deadline = time.monotonic() + seconds
    wake = state.event()
    while True:
        if state.pending_dispatch:
            state.pending_dispatch = False
            commands = _dispatch_pending(state)
            if commands:
                return commands
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return []
        wake.clear()
        if state.pending_dispatch:      # queued between the check and clear()
            continue
        try:
            await asyncio.wait_for(wake.wait(), timeout=remaining)
        except asyncio.TimeoutError:
            return []


# --------------------------------------------------------------------- flush

def flush(state: ServerState) -> bool:
    """Write everything buffered for this server in one transaction."""
    if not state.buffered():
        return True
    from .bridge import _optional, _store_events, _store_identities, _store_punishments

    evidence = dict(state.evidence)
    identity_rows = list(state.identity_rows)
    event_blocks = list(state.event_blocks)
    punish_blocks = list(state.punish_blocks)
    snapshot = state.snapshot if state.dirty else None
    row = state.row
    view = {"workspace": row["workspace"], **state.db_cursors}
    degraded: list[str] = []
    try:
        with db.transaction() as cur:
            cur.execute("DELETE FROM nx_stream_frames WHERE server=%s AND updated<%s", (state.id, now() - 20))
            cur.execute("DELETE FROM nx_stream_viewers WHERE server=%s AND expires<=%s", (state.id, now()))
            if snapshot is not None:
                cur.execute("UPDATE nx_servers SET last_seen=%s, snapshot=%s, boot=%s, sequence=%s WHERE id=%s",
                            (row.get("last_seen"), db.jsonb(snapshot), row.get("boot"), row.get("sequence"), state.id))
            for item in evidence.values():
                cur.execute(
                    """INSERT INTO nx_evidence VALUES(%s,%s,%s,%s)
                       ON CONFLICT(server,id) DO UPDATE SET body=EXCLUDED.body, updated=EXCLUDED.updated
                       WHERE nx_evidence.body IS DISTINCT FROM EXCLUDED.body""",
                    (state.id, item["id"], db.jsonb(item), now()),
                )
            if identity_rows:
                held = _optional(cur, degraded, "identities", _store_identities, view, state.id,
                                 {"rows": identity_rows, "cursor": row.get("identity_cursor")})
                if "identities" not in degraded:
                    view["identity_cursor"] = held
            for block in event_blocks:
                held = _optional(cur, degraded, "events", _store_events, view, state.id, block, block["sequence"])
                if "events" in degraded:
                    break
                view["event_cursor"], view["event_boot"] = held, block["boot"]
            for block in punish_blocks:
                held = _optional(cur, degraded, "punishments", _store_punishments, view, state.id, block)
                if "punishments" in degraded:
                    break
                view["punish_cursor"], view["punish_boot"] = held, block["boot"]
    except Exception as error:  # noqa: BLE001 - keep the buffer and retry later
        log.warning("[NexusAC hub] flush for %s failed, will retry: %s", state.id, error)
        _cap(state)
        return False

    # Only what was written is removed; anything that arrived meanwhile stays.
    for key in evidence:
        if state.evidence.get(key) is evidence[key]:
            del state.evidence[key]
    del state.identity_rows[:len(identity_rows)]
    del state.event_blocks[:len(event_blocks)]
    del state.punish_blocks[:len(punish_blocks)]
    if snapshot is not None and state.snapshot is snapshot:
        state.dirty = False
    state.db_cursors = {k: view.get(k) for k in CURSOR_FIELDS}
    state.degraded = degraded
    state.last_flush = time.time()
    try:
        maintenance.sweep()          # hourly at most; the database is awake now anyway
    except Exception as error:  # noqa: BLE001
        log.warning("[NexusAC hub] retention sweep failed: %s", error)
    return True


def _cap(state: ServerState) -> None:
    """While the database is unreachable, keep memory bounded: oldest events go first."""
    while sum(len(b["rows"]) for b in state.event_blocks) > MAX_BUFFERED_EVENTS * 5 and state.event_blocks:
        state.event_blocks.pop(0)
    if len(state.identity_rows) > MAX_BUFFERED_IDENTITIES * 5:
        del state.identity_rows[:len(state.identity_rows) - MAX_BUFFERED_IDENTITIES * 5]


def flush_workspace(workspace: str) -> None:
    for state in states_in(workspace):
        if state.buffered():
            flush(state)


def flush_all() -> None:
    with _lock:
        states = list(_by_id.values())
    for state in states:
        if state.buffered():
            flush(state)


def flush_due() -> None:
    with _lock:
        states = list(_by_id.values())
    for state in states:
        if state.buffered() and time.time() - state.last_flush >= FLUSH_SECONDS:
            flush(state)


async def flusher() -> None:
    while True:
        await asyncio.sleep(30)
        try:
            await asyncio.to_thread(flush_due)
        except Exception as error:  # noqa: BLE001
            log.warning("[NexusAC hub] periodic flush failed: %s", error)


def reset_for_tests() -> None:
    with _lock:
        _by_id.clear()
        _by_token.clear()
        _bad_tokens.clear()


__all__ = ["by_token", "by_id", "accept_sync", "long_poll", "command_queued", "flush", "flush_all",
           "flush_workspace", "flusher", "forget", "last_seen", "snapshot_of", "HttpError"]
