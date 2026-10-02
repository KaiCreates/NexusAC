"""Keep the database a fixed size.

Supabase's free database filled up because almost every table only ever grew:
screenshots (stored as base64 text, up to ~1.4 MB each), evidence, the command
history and the audit log. A free Neon database is 0.5 GB, so retention is not
optional. `sweep()` runs from the bridge sync at most once an hour per worker
and is a handful of indexed DELETEs.

Windows (days), all overridable with environment variables:
    MEDIA_RETENTION_DAYS     14   screenshots (also capped at MEDIA_KEEP per server)
    EVIDENCE_RETENTION_DAYS  30
    COMMAND_RETENTION_DAYS    7
    AUDIT_RETENTION_DAYS     90
And a hard guard: above DB_SOFT_LIMIT_MB (default 400) the oldest events and
screenshots are trimmed harder until the database is back under it.
"""
from __future__ import annotations

import logging
import os
import threading
import time

from . import db

log = logging.getLogger("nexusac.maintenance")

DAY = 86400


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


MEDIA_DAYS = _env_int("MEDIA_RETENTION_DAYS", 14)
MEDIA_KEEP = _env_int("MEDIA_KEEP", 300)
EVIDENCE_DAYS = _env_int("EVIDENCE_RETENTION_DAYS", 30)
COMMAND_DAYS = _env_int("COMMAND_RETENTION_DAYS", 7)
AUDIT_DAYS = _env_int("AUDIT_RETENTION_DAYS", 90)
SOFT_LIMIT_MB = _env_int("DB_SOFT_LIMIT_MB", 400)
EVERY_SECONDS = 3600

_lock = threading.Lock()
_last = 0.0


def _size_mb(cur) -> float:
    cur.execute("SELECT pg_database_size(current_database()) AS bytes")
    return int(cur.fetchone()["bytes"]) / 1048576


def sweep(force: bool = False) -> dict:
    """Delete everything past its retention window. Returns what it removed."""
    global _last
    with _lock:
        if not force and time.time() - _last < EVERY_SECONDS:
            return {}
        _last = time.time()
    t = int(time.time())
    removed: dict[str, int] = {}
    with db.transaction() as cur:
        def run(label: str, sql: str, args: tuple = ()) -> None:
            cur.execute(sql, args)
            removed[label] = removed.get(label, 0) + max(cur.rowcount, 0)

        run("media", "DELETE FROM nx_media WHERE created < %s", (t - MEDIA_DAYS * DAY,))
        # Per-server cap on screenshots, newest kept.
        run("media", """DELETE FROM nx_media m USING (
                           SELECT server, evidence_id, slot, row_number() OVER
                                  (PARTITION BY server ORDER BY created DESC) AS rank
                           FROM nx_media) old
                        WHERE m.server = old.server AND m.evidence_id = old.evidence_id
                          AND m.slot = old.slot AND old.rank > %s""", (MEDIA_KEEP,))
        run("evidence", "DELETE FROM nx_evidence WHERE updated < %s", (t - EVIDENCE_DAYS * DAY,))
        run("commands", "DELETE FROM nx_commands WHERE created < %s", (t - COMMAND_DAYS * DAY,))
        run("audit", "DELETE FROM nx_audit WHERE at < %s", (t - AUDIT_DAYS * DAY,))
        run("limits", "DELETE FROM nx_limits WHERE expires < %s", (t,))
        run("sessions", "DELETE FROM nx_sessions WHERE expires < %s", (t,))
        run("invites", "DELETE FROM nx_invites WHERE expires < %s", (t,))
        run("boots", "DELETE FROM nx_bridge_boots WHERE at < %s", (t - 30 * DAY,))
        run("inventory", "DELETE FROM nx_inventory_views WHERE created < %s", (t - 600,))

        # Hard guard: still too big -> shorten the two big tables' windows.
        size = _size_mb(cur)
        for days in (3, 1):
            if size <= SOFT_LIMIT_MB:
                break
            log.warning("[NexusAC] database is %.0f MB (limit %d MB): trimming events and "
                        "screenshots older than %d day(s)", size, SOFT_LIMIT_MB, days)
            run("events", "DELETE FROM nx_events WHERE at < %s", (t - days * DAY,))
            run("media", "DELETE FROM nx_media WHERE created < %s", (t - days * DAY,))
            size = _size_mb(cur)
        removed["size_mb"] = round(size)
    if any(v for k, v in removed.items() if k != "size_mb"):
        log.info("[NexusAC] retention sweep removed %s", removed)
    return removed
