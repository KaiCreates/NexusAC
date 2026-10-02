"""Set (or reset) a website account's password.

There is no email service, so this is how an owner resets a password, and how
accounts copied from the Supabase era get their first one.

    python scripts/set_password.py someone@example.com
        (asks for the new password; uses DATABASE_URL from .env / the environment)

    python scripts/set_password.py --list
        (shows every account and whether it has a password yet)
"""
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db, local_auth  # noqa: E402

MIN_PASSWORD = 12


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    db.ensure_schema()
    if sys.argv[1] == "--list":
        for row in db.query("SELECT email, name, password_hash IS NOT NULL AS has FROM nx_users ORDER BY email"):
            print(("  ok      " if row["has"] else "  NO PASS ") + row["email"] + "  (" + row["name"] + ")")
        return 0
    email = sys.argv[1].strip().lower()
    if not db.one("SELECT 1 AS x FROM nx_users WHERE lower(email)=%s", (email,)):
        print("No account with that email. They can register on the website instead.")
        return 1
    password = getpass.getpass("New password for %s: " % email)
    if len(password) < MIN_PASSWORD:
        print("Use at least %d characters." % MIN_PASSWORD)
        return 1
    if getpass.getpass("Again: ") != password:
        print("The two passwords differ.")
        return 1
    local_auth.set_password(email, password)
    # Sign them out everywhere: an old session should not outlive a reset.
    db.execute("DELETE FROM nx_sessions WHERE user_id=(SELECT id FROM nx_users WHERE lower(email)=%s)", (email,))
    print("Password set for %s." % email)
    return 0


if __name__ == "__main__":
    sys.exit(main())
