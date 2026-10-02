"""Inventory lookups: queue -> game server answers via /bridge/inventory -> page polls.

Runs the real endpoints against an in-memory fake database.

    python tests/inventorycheck.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for key in ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SECRET_KEY", "DATABASE_URL"):
    os.environ.setdefault(key, "http://test.invalid" if key.startswith("SUPABASE_URL") else "test")

from contextlib import contextmanager  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app import api_routes, bridge, db, security  # noqa: E402
from app.main import app  # noqa: E402

SERVER = "11111111-1111-1111-1111-111111111111"
TOKEN = "k" * 43
commands, views = {}, {}
server_row = {"id": SERVER, "name": "Test", "workspace": "w1", "token_hash": security.sha256(TOKEN),
              "last_seen": 10**10, "sequence": 1, "boot": "b",
              "snapshot": {"players": [{"src": 3, "sessionKey": "sess-3", "name": "Kai"}]}}


class Cursor:
    def __init__(self):
        self.result = None

    def execute(self, sql, args=()):
        s = " ".join(sql.split())
        self.result = None
        if s.startswith("SELECT body FROM nx_commands"):
            c = commands.get(args[0])
            self.result = [{"body": c["body"]}] if c and c["server"] == args[1] else []
        elif s.startswith("DELETE FROM nx_inventory_views"):
            for k in [k for k, v in views.items() if v["created"] < args[1]]:
                del views[k]
        elif s.startswith("INSERT INTO nx_inventory_views"):
            views[args[1]] = {"server": args[0], "operation": args[2], "ok": args[3], "message": args[4],
                              "body": args[5], "created": args[6]}
        elif s.startswith("INSERT INTO nx_commands"):
            commands[args[0]] = {"server": args[1], "actor": args[2], "body": args[4], "status": "pending", "result": None}
        else:
            raise AssertionError("unexpected SQL: " + s[:90])

    def fetchone(self):
        return self.result[0] if self.result else None

    def fetchall(self):
        return self.result or []


@contextmanager
def fake_transaction():
    yield Cursor()


def fake_one(sql, args=()):
    s = " ".join(sql.split())
    if "FROM nx_servers WHERE token_hash" in s:
        return server_row if args[0] == server_row["token_hash"] else None
    if "FROM nx_servers WHERE id=%s AND workspace" in s:
        return server_row if args[0] == SERVER and args[1] == "w1" else None
    if s.startswith("SELECT actor, status, result FROM nx_commands"):
        c = commands.get(args[0])
        return {"actor": c["actor"], "status": c["status"], "result": c["result"]} if c and c["server"] == args[1] else None
    if s.startswith("SELECT operation, ok, message, body, created FROM nx_inventory_views"):
        v = views.get(args[1])
        return v if v and v["server"] == args[0] else None
    raise AssertionError("unexpected SQL: " + s[:90])


for mod in (db, api_routes.db, bridge.db):
    mod.one, mod.transaction, mod.ensure_schema = fake_one, fake_transaction, lambda: None
    mod.jsonb = lambda value: value
for mod in (security, api_routes, bridge):
    mod.rate = lambda *a, **k: None
api_routes.audit = lambda *a, **k: None
api_routes.origin_check = lambda request: None
user = {"workspace": "w1", "role": "moderator", "user_id": "u1", "name": "Mod"}
api_routes.authenticated = lambda request: dict(user)

client = TestClient(app)
passed = failed = 0


def check(label, got, want):
    global passed, failed
    ok = got == want
    passed, failed = passed + ok, failed + (not ok)
    print(("  PASS  " if ok else "  FAIL  ") + "%-62s %s" % (label, got if ok else "got %r wanted %r" % (got, want)))


def queue(body):
    return client.post("/api/control/servers/%s/commands" % SERVER, json={"type": "inventory", **body})


def upload(command_id, body, op="view"):
    return client.post("/api/control/bridge/inventory", headers={"Authorization": "Bearer " + TOKEN},
                       json={"commandId": command_id, "operation": op, "ok": True, "body": body})


def poll(command_id):
    return client.get("/api/control/servers/%s/inventory/%s" % (SERVER, command_id))


print("== queue ==")
r = queue({"operation": "search", "query": "kai"})
check("moderator can queue a search", r.status_code, 202)
search_id = r.json()["id"]
check("...stored as an inventory command", commands[search_id]["body"]["type"], "inventory")
check("player lookup with the live session", queue({"operation": "player", "target": 3, "session": "sess-3"}).status_code, 202)
check("player lookup with a stale session refused", queue({"operation": "player", "target": 3, "session": "old"}).status_code, 409)
check("view without identifier refused", queue({"operation": "view"}).status_code, 400)
check("SQL-ish identifier refused", queue({"operation": "view", "identifier": "x' OR 1=1"}).status_code, 400)
user["role"] = "viewer"
check("viewer role refused", queue({"operation": "search"}).status_code, 403)
user["role"] = "moderator"

print("== poll before the server answers ==")
check("pending while the game server has not answered", poll(search_id).json()["status"], "pending")

print("== bridge upload ==")
check("bad key refused", client.post("/api/control/bridge/inventory", headers={"Authorization": "Bearer " + "x" * 43},
                                     json={"commandId": search_id, "operation": "search", "body": {}}).status_code, 401)
check("unknown command id refused", upload("99999999-9999-9999-9999-999999999999", {}).status_code, 404)
commands["22222222-2222-2222-2222-222222222222"] = {"server": SERVER, "actor": "u1", "body": {"type": "kick"},
                                                    "status": "pending", "result": None}
check("upload against a non-inventory command refused", upload("22222222-2222-2222-2222-222222222222", {}).status_code, 404)
r = upload(search_id, {"query": "kai", "rows": [{"identifier": "char1:abc", "name": "Kai Test", "online": True}]}, "search")
check("matching upload accepted", r.status_code, 200)

print("== poll after ==")
d = poll(search_id).json()
check("ready", d["status"], "ready")
check("...with the server's rows", d["body"]["rows"][0]["identifier"], "char1:abc")
user["user_id"] = "u2"
check("another staff member cannot read it", poll(search_id).status_code, 404)
user["user_id"] = "u1"
check("malformed id is a 404, not a crash", poll("not-a-uuid").status_code, 404)

print()
print("%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
