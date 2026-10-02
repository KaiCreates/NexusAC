"""Real-Postgres check for the move off Supabase: every migration applies on a
plain Postgres (no Supabase roles), built-in sign-up/sign-in work end to end,
and the retention sweep deletes what it should.

Needs a disposable database (it creates and deletes rows):

    DATABASE_URL=postgresql://... python tests/postgrescheck.py

Without DATABASE_URL it starts an embedded Postgres via `pgserver` if installed.
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if not os.environ.get("DATABASE_URL"):
    import pgserver  # noqa: E402
    _pg = pgserver.get_server(tempfile.mkdtemp(prefix="nxpg-"), cleanup_mode="stop")
    os.environ["DATABASE_URL"] = _pg.get_uri()
os.environ.setdefault("APP_URL", "http://testserver")

from fastapi.testclient import TestClient  # noqa: E402

from app import db, local_auth, maintenance  # noqa: E402
from app.main import app  # noqa: E402

passed = failed = 0


def check(label, got, want):
    global passed, failed
    ok = got == want
    passed, failed = passed + ok, failed + (not ok)
    print(("  PASS  " if ok else "  FAIL  ") + "%-60s %s" % (label, got if ok else "got %r wanted %r" % (got, want)))


print("== migrations on plain Postgres ==")
db.run_migrations()
db.run_migrations()   # idempotent
db.ensure_schema()
tables = {r["table_name"] for r in db.query(
    "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'nx_%%'")}
check("all migrations applied twice without a Supabase role", "nx_inventory_views" in tables and "nx_events" in tables, True)
check("password_hash column exists", bool(db.one(
    "SELECT 1 AS x FROM information_schema.columns WHERE table_name='nx_users' AND column_name='password_hash'")), True)

print("== built-in sign-in ==")
stamp = int(time.time() * 1000)
email, pw = "owner%d@nexusac.test" % stamp, "correct-horse-battery-9"
site = TestClient(app, base_url="http://testserver", headers={"Origin": "http://testserver"})
r = site.post("/api/control/auth/register", json={"email": email, "password": pw, "name": "Owner"})
check("register", r.status_code, 200)
check("...signed in straight away (session cookie)", "nexus_session" in r.headers.get("set-cookie", ""), True)
check("...workspace usable", site.get("/api/control/workspace").status_code, 200)
row = db.one("SELECT password_hash FROM nx_users WHERE email=%s", (email,))
check("...password stored hashed, not plain", row["password_hash"].startswith("scrypt$") and pw not in row["password_hash"], True)
check("register same email again refused", site.post("/api/control/auth/register",
      json={"email": email.upper(), "password": pw, "name": "x"}).status_code, 409)
fresh = TestClient(app, base_url="http://testserver", headers={"Origin": "http://testserver"})
check("login with right password", fresh.post("/api/control/auth/login", json={"email": email, "password": pw}).status_code, 200)
check("login with wrong password", fresh.post("/api/control/auth/login", json={"email": email, "password": pw + "x"}).status_code, 401)
check("login with unknown email (same answer)", fresh.post("/api/control/auth/login",
      json={"email": "nobody%d@nexusac.test" % stamp, "password": pw}).status_code, 401)

# An account copied from Supabase: no password until the owner sets one.
legacy = "legacy%d@nexusac.test" % stamp
db.execute("INSERT INTO nx_users(id,email,name,created) VALUES(gen_random_uuid(),%s,'Legacy',%s)", (legacy, int(time.time())))
check("copied account without a password cannot sign in",
      fresh.post("/api/control/auth/login", json={"email": legacy, "password": pw}).status_code, 403)
local_auth.set_password(legacy, "another-long-password-1")
check("...after set_password it is a normal hash", local_auth.verify_password(
    "another-long-password-1", db.one("SELECT password_hash FROM nx_users WHERE email=%s", (legacy,))["password_hash"]), True)
check("password reset endpoint answers without email",
      fresh.post("/api/control/reset", json={"email": email}).status_code, 200)

print("== retention sweep ==")
ws = db.one("SELECT workspace FROM nx_members m JOIN nx_users u ON u.id=m.user_id WHERE u.email=%s", (email,))["workspace"]
server = db.one("INSERT INTO nx_servers(id,workspace,name,token_hash,created) VALUES(gen_random_uuid(),%s,'S',%s,%s) RETURNING id",
                (ws, "h%d" % stamp, int(time.time())))["id"]
old, new = int(time.time()) - 60 * 86400, int(time.time())
for i in range(3):
    db.execute("INSERT INTO nx_media VALUES(%s,%s,0,'data:x',%s)", (server, "old%d" % i, old))
    db.execute("INSERT INTO nx_media VALUES(%s,%s,0,'data:x',%s)", (server, "new%d" % i, new))
db.execute("INSERT INTO nx_commands(id,server,actor,actor_name,body,created,expires) VALUES(gen_random_uuid(),%s,gen_random_uuid(),'a','{}',%s,%s)", (server, old, old))
db.execute("INSERT INTO nx_evidence VALUES(%s,'oldcase','{}',%s)", (server, old))
db.execute("INSERT INTO nx_evidence VALUES(%s,'newcase','{}',%s)", (server, new))
removed = maintenance.sweep(force=True)
check("old screenshots removed", db.one("SELECT count(*) AS n FROM nx_media WHERE server=%s AND evidence_id LIKE 'old%%'", (server,))["n"], 0)
check("...new ones kept", db.one("SELECT count(*) AS n FROM nx_media WHERE server=%s AND evidence_id LIKE 'new%%'", (server,))["n"], 3)
check("old evidence removed, new kept", [r["id"] for r in db.query("SELECT id FROM nx_evidence WHERE server=%s ORDER BY id", (server,))], ["newcase"])
check("old commands removed", db.one("SELECT count(*) AS n FROM nx_commands WHERE server=%s", (server,))["n"], 0)
check("sweep reports database size", "size_mb" in removed, True)
check("a second sweep within the hour is skipped", maintenance.sweep(), {})

db.execute("DELETE FROM nx_workspaces WHERE id=%s", (ws,))
db.execute("DELETE FROM nx_users WHERE email IN (%s,%s)", (email, legacy))
print()
print("%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
