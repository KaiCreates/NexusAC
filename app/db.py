"""Postgres access.

Supabase's direct database host is IPv6-only, so this connects through the
Supavisor transaction pooler. Prepared statements are disabled because
transaction-mode pooling reuses backends between statements and pgbouncer-style
poolers cannot carry a prepared statement across that boundary.
"""
from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterable, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from . import config

_lock = threading.Lock()
_conn: psycopg.Connection | None = None


def _connect() -> psycopg.Connection:
    return psycopg.connect(
        config.DATABASE_URL,
        row_factory=dict_row,
        autocommit=True,
        prepare_threshold=None,
        connect_timeout=10,
        application_name="nexusac-web",
    )


@contextmanager
def connection():
    """Yield the shared connection, reconnecting if it died between invocations.

    Serverless functions are re-entered warm, so keeping one connection alive
    avoids a TLS handshake per request; the lock keeps concurrent requests inside
    one worker from interleaving on the same socket.
    """
    global _conn
    with _lock:
        # A sleeping pooler or a dropped idle socket should not turn one
        # heartbeat into a 503. Reconnect failures are retried here as well as
        # query failures, with a short bounded delay that does not hold the
        # connection open indefinitely.
        for attempt in (1, 2, 3):
            try:
                if _conn is None or _conn.closed:
                    _conn = _connect()
                yield _conn
                return
            except (psycopg.OperationalError, psycopg.InterfaceError):
                try:
                    _conn.close()
                except Exception:
                    pass
                _conn = None
                if attempt == 3:
                    raise
                time.sleep(0.15 * attempt)


def query(sql: str, args: Sequence[Any] = ()) -> list[dict]:
    # psycopg only scans for placeholders when parameters are supplied, so an
    # empty sequence must become None or a literal % in the SQL is misread.
    with connection() as conn, conn.cursor() as cur:
        cur.execute(sql, tuple(args) or None)
        return cur.fetchall() if cur.description else []


def execute(sql: str, args: Sequence[Any] = ()) -> int:
    with connection() as conn, conn.cursor() as cur:
        cur.execute(sql, tuple(args) or None)
        return cur.rowcount


def one(sql: str, args: Sequence[Any] = ()) -> dict | None:
    rows = query(sql, args)
    return rows[0] if rows else None


@contextmanager
def transaction():
    """A real database transaction. The bridge needs one: boot registration,
    sequence advance and command dispatch have to be all-or-nothing so two
    overlapping polls cannot hand the same command out twice."""
    with connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                yield cur


def jsonb(value: Any) -> Jsonb:
    """Postgres jsonb rejects \u0000, which FiveM player names occasionally carry."""
    cleaned = json.loads(json.dumps(value, ensure_ascii=True).replace("\u0000", ""))
    return Jsonb(cleaned)


def run_migrations(statements: Iterable[str] | None = None) -> None:
    """Apply every migration in filename order.

    All of them are written to be safe to re-run (CREATE TABLE IF NOT EXISTS,
    ADD COLUMN IF NOT EXISTS), so there is no version table to keep in step --
    running the whole set is the same as running the missing ones.
    """
    from pathlib import Path

    folder = Path(__file__).resolve().parent.parent / "migrations"
    with connection() as conn, conn.cursor() as cur:
        for path in sorted(folder.glob("*.sql")):
            cur.execute(path.read_text(encoding="utf-8"))
