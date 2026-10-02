"""Copy the website's data from the old (Supabase) database into the new one.

    SOURCE_DATABASE_URL=<old Supabase URL>  DATABASE_URL=<new Neon URL>  python scripts/copy_database.py

(Both can live in .env, which is gitignored.) Safe to re-run: rows that are
already there are skipped. Only data inside the retention windows is copied,
so the new database does not start out full. Not copied: sign-in sessions,
rate-limit counters, live-stream frames and inventory lookups (all transient).

Staff accounts, workspaces, members, servers (with their API keys, so the game
server keeps working without a new key), evidence, screenshots, the audit log,
identities, events and punishments are copied. Supabase kept the passwords, so
every copied account needs one set with scripts/set_password.py before it can
sign in.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402
from psycopg.types.json import Jsonb  # noqa: E402

from app import config, db, maintenance  # noqa: E402

DAY = 86400
NOW = int(time.time())
# (table, WHERE clause on the source) in foreign-key order.
TABLES = [
    ("nx_users", ""),
    ("nx_workspaces", ""),
    ("nx_members", ""),
    ("nx_servers", ""),
    ("nx_bridge_boots", "WHERE at >= %d" % (NOW - 30 * DAY)),
    ("nx_invites", "WHERE expires > %d" % NOW),
    ("nx_commands", "WHERE created >= %d" % (NOW - maintenance.COMMAND_DAYS * DAY)),
    ("nx_evidence", "WHERE updated >= %d" % (NOW - maintenance.EVIDENCE_DAYS * DAY)),
    ("nx_media", "WHERE created >= %d" % (NOW - maintenance.MEDIA_DAYS * DAY)),
    ("nx_audit", "WHERE at >= %d" % (NOW - maintenance.AUDIT_DAYS * DAY)),
    ("nx_identities", ""),
    ("nx_identity_marks", ""),
    ("nx_events", "WHERE at >= %d" % (NOW - int(os.environ.get("EVENT_RETENTION_DAYS", "7")) * DAY)),
    ("nx_punishments", ""),
]
BATCH = 200


def columns(conn, table):
    with conn.cursor() as cur:
        cur.execute("SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position", (table,))
        return [r["column_name"] for r in cur.fetchall()]


def wrap(value):
    return Jsonb(value) if isinstance(value, (dict, list)) else value


def main() -> int:
    source_url = os.environ.get("SOURCE_DATABASE_URL", "").strip()
    if not source_url:
        print("Set SOURCE_DATABASE_URL (the old Supabase connection string) and DATABASE_URL (the new one).")
        return 2
    if source_url == config.DATABASE_URL:
        print("SOURCE_DATABASE_URL and DATABASE_URL are the same database; nothing to do.")
        return 2
    print("Preparing the new database (migrations)...")
    db.ensure_schema()
    try:
        source = psycopg.connect(source_url, row_factory=dict_row, connect_timeout=20, prepare_threshold=None)
    except Exception as error:  # noqa: BLE001
        print("Could not connect to the old database: %s" % error)
        print("If Supabase has locked the project, start fresh instead: register again on the new site.")
        return 1
    target = psycopg.connect(config.DATABASE_URL, row_factory=dict_row, autocommit=False, prepare_threshold=None)
    total = 0
    for table, where in TABLES:
        src_cols = columns(source, table)
        if not src_cols:
            print("  %-20s not in the old database, skipped" % table)
            continue
        cols = [c for c in src_cols if c in set(columns(target, table))]
        names = ", ".join('"%s"' % c for c in cols)
        insert = 'INSERT INTO %s (%s) VALUES (%s) ON CONFLICT DO NOTHING' % (
            table, names, ", ".join(["%s"] * len(cols)))
        copied = 0
        with source.cursor(name="copy_" + table) as read:
            read.itersize = BATCH
            read.execute("SELECT %s FROM %s %s" % (names, table, where))
            while True:
                rows = read.fetchmany(BATCH)
                if not rows:
                    break
                with target.cursor() as write:
                    write.executemany(insert, [[wrap(r[c]) for c in cols] for r in rows])
                    copied += max(write.rowcount, 0)
                target.commit()
        total += copied
        print("  %-20s %6d new row(s)" % (table, copied))
    source.close()
    target.close()
    print("Done: %d row(s) copied." % total)
    print("Next: give every account a password -> python scripts/set_password.py --list")
    return 0


if __name__ == "__main__":
    sys.exit(main())
