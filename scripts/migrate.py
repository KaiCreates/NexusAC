"""Create (or update) the website's tables in Supabase. Safe to re-run."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402

if __name__ == "__main__":
    db.run_migrations()
    tables = db.query(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name LIKE 'nx_%' ORDER BY table_name"
    )
    print("Migrated. Tables now present:")
    for row in tables:
        print("  -", row["table_name"])
