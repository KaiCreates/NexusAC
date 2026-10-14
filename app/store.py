"""Persistent state: accounts and server keys. Nothing else is stored.

The whole state is ONE small JSON document. It is read once at startup and
written only when an owner changes an account or a server, so a normal panel
session touches the database zero times.

DATABASE_URL set   -> one row in Postgres (table nxw_state), for hosts with an
                      ephemeral disk (Render).
DATABASE_URL unset -> a local file (DATA_FILE, default ./data.json).
"""
import asyncio
import json
import os
import secrets

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DATA_FILE = os.environ.get("DATA_FILE", "data.json")

state: dict = {"users": {}, "servers": {}, "secret": ""}
_lock = asyncio.Lock()


def _db_load() -> dict | None:
    import psycopg

    with psycopg.connect(DATABASE_URL, autocommit=True, connect_timeout=15) as con:
        con.execute("CREATE TABLE IF NOT EXISTS nxw_state (id int PRIMARY KEY, doc text NOT NULL)")
        row = con.execute("SELECT doc FROM nxw_state WHERE id = 1").fetchone()
        return json.loads(row[0]) if row else None


def _db_save(doc: str) -> None:
    import psycopg

    with psycopg.connect(DATABASE_URL, autocommit=True, connect_timeout=15) as con:
        con.execute(
            "INSERT INTO nxw_state (id, doc) VALUES (1, %s) ON CONFLICT (id) DO UPDATE SET doc = EXCLUDED.doc",
            (doc,),
        )


def _file_load() -> dict | None:
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def _file_save(doc: str) -> None:
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(doc)
    os.replace(tmp, DATA_FILE)


async def load() -> None:
    loaded = await asyncio.to_thread(_db_load if DATABASE_URL else _file_load)
    if loaded:
        state.update(loaded)
    state.setdefault("users", {})
    state.setdefault("servers", {})
    if not state.get("secret"):
        state["secret"] = secrets.token_hex(32)
        await save()


async def save() -> None:
    async with _lock:
        doc = json.dumps(state, separators=(",", ":"))
        await asyncio.to_thread(_db_save if DATABASE_URL else _file_save, doc)
