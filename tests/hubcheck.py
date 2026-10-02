"""The two promises of app/hub.py, checked against a real website process and a
real Postgres:

  1. a staff command reaches the game server well inside 3 seconds
     (long poll answered from memory), and its result is visible right after;
  2. steady-state traffic -- game-server syncs, the held command channel and an
     open dashboard polling -- does not touch the database at all, so a
     scale-to-zero database (Neon free) can sleep between batch writes.

    python tests/hubcheck.py      (DATABASE_URL, or an embedded `pgserver`)
"""
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if not os.environ.get("DATABASE_URL"):
    import pgserver  # noqa: E402
    _pg = pgserver.get_server(tempfile.mkdtemp(prefix="nxhub-"), cleanup_mode="stop")
    os.environ["DATABASE_URL"] = _pg.get_uri()
PORT = 38117
SITE = "http://127.0.0.1:%d" % PORT
os.environ["APP_URL"] = SITE

import httpx  # noqa: E402
import uvicorn  # noqa: E402

from app import db, hub  # noqa: E402
from app.main import app  # noqa: E402

passed = failed = 0


def check(label, got, want=True):
    global passed, failed
    ok = got == want
    passed, failed = passed + ok, failed + (not ok)
    print(("  PASS  " if ok else "  FAIL  ") + "%-64s %s" % (label, got if ok else "got %r wanted %r" % (got, want)))


# Count every trip to the database.
trips = {"n": 0}
_real_connection = db.connection


class _Counted:
    def __init__(self):
        self.inner = _real_connection()

    def __enter__(self):
        trips["n"] += 1
        return self.inner.__enter__()

    def __exit__(self, *exc):
        return self.inner.__exit__(*exc)


db.connection = _Counted

db.run_migrations()
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
threading.Thread(target=server.run, daemon=True).start()
for _ in range(100):
    if server.started:
        break
    time.sleep(0.05)

stamp = int(time.time())
staff = httpx.Client(base_url=SITE, timeout=40, headers={"Origin": SITE})
staff.post("/api/control/auth/register", json={"email": "hub%d@nexusac.test" % stamp,
                                                "password": "correct-horse-battery-9", "name": "Owner"})
created = staff.post("/api/control/servers", json={"name": "Kai RP"}).json()
SID, TOKEN = created["id"], created["token"]
game = httpx.Client(base_url=SITE + "/api/control/bridge", timeout=40,
                    headers={"Authorization": "Bearer " + TOKEN})
seq = {"n": 0, "ev": 0}
acks = []


def sync(events=0, evidence=None):
    seq["n"] += 1
    snap = {"overview": {"mode": "enforce", "version": "0.2.0", "uptime": 60, "online": 1},
            "players": [{"src": 1, "name": "Kaiii", "sessionKey": "sess-1", "ping": 30 + seq["n"]}],
            "eventLog": {"boot": "boot-1", "cursor": seq["ev"] + events,
                         "rows": [{"seq": seq["ev"] + 1 + i, "at": int(time.time()), "type": "playerDamaged",
                                   "sender": "1", "senderName": "Kaiii", "data": {}} for i in range(events)]}}
    seq["ev"] += events
    if evidence:
        snap["evidence"] = evidence
    body = {"protocol": 1, "boot": "boot-1", "sequence": seq["n"], "sentAt": int(time.time()),
            "snapshot": snap, "acknowledgements": list(acks)}
    acks.clear()
    return game.post("/sync", json=body)


print("== first contact (expected to use the database) ==")
r = sync(events=5, evidence=[{"id": "boot-1:NX-E-1", "at": int(time.time()), "detection": "Godmode"}])
check("first sync accepted", r.status_code, 200)
page = staff.get("/api/control/servers/%s/snapshot" % SID).json()
versions = "?sv=%s&ev=%s&cv=%s" % (page["snapshotVersion"], page["evidenceVersion"], page["commandsVersion"])
check("dashboard shows the live player", page["snapshot"]["players"][0]["name"], "Kaiii")
check("...and the buffered evidence (flushed on demand)", [e["id"] for e in page["evidence"]], ["boot-1:NX-E-1"])
hub.LONG_POLL_SECONDS = 1
game.post("/wait", json={"protocol": 1})   # settles "unknown pending" after start

print("== steady state: no database at all ==")
before = trips["n"]
for _ in range(5):
    check("sync with 40 events accepted", sync(events=40).status_code, 200)
    r = game.post("/wait", json={"protocol": 1})
    check("held command channel returns empty, held=true", (r.json()["commands"], r.json()["held"]), ([], True))
    poll = staff.get("/api/control/servers/%s/snapshot%s" % (SID, versions)).json()
    versions = "?sv=%s&ev=%s&cv=%s" % (poll["snapshotVersion"], poll["evidenceVersion"], poll["commandsVersion"])
check("database round trips during 5 syncs + 5 waits + 5 dashboard polls", trips["n"] - before, 0)
check("dashboard sees the newest snapshot from memory", poll["snapshot"]["players"][0]["ping"], 30 + seq["n"])
unchanged = staff.get("/api/control/servers/%s/snapshot%s" % (SID, versions)).json()
check("an unchanged poll sends nothing back", (unchanged["snapshot"], unchanged["evidence"], unchanged["commands"]),
      (None, None, None))

print("== a staff command reaches the game server inside 3 s ==")
hub.LONG_POLL_SECONDS = 25
got = {}


def hold():
    started = time.time()
    got["reply"] = game.post("/wait", json={"protocol": 1}).json()
    got["at"] = time.time()
    got["held_for"] = got["at"] - started


waiter = threading.Thread(target=hold)
waiter.start()
time.sleep(1.0)                                    # the game server is now parked on /wait
sent_at = time.time()
queued = staff.post("/api/control/servers/%s/commands" % SID,
                    json={"type": "warn", "target": 1, "session": "sess-1", "reason": "hub latency test"})
check("command queued", queued.status_code, 202)
waiter.join(30)
delivery = got.get("at", 99) - sent_at
check("delivered to the game server", [c.get("type") for c in got["reply"]["commands"]], ["warn"])
check("...in under 1 s (was up to 15 s)", delivery < 1.0, True)
print("        delivery took %.0f ms" % (delivery * 1000))

acks.append({"id": got["reply"]["commands"][0]["id"], "ok": True, "message": "Warned Kaiii."})
sync()
ack_seen = time.time() - sent_at
cmds = staff.get("/api/control/servers/%s/snapshot%s" % (SID, versions)).json()["commands"]
check("result visible on the dashboard right after the ack", (cmds or [{}])[0].get("status"), "succeeded")
check("...whole round trip (queue -> game -> result) under 3 s", ack_seen < 3.0, True)
print("        round trip took %.0f ms" % (ack_seen * 1000))

print("== batch write ==")
check("events are buffered, not yet in the database",
      db.one("SELECT count(*) AS n FROM nx_events WHERE server=%s", (SID,))["n"] <= 5, True)
hub.flush_all()
check("flush writes all buffered events", db.one("SELECT count(*) AS n FROM nx_events WHERE server=%s", (SID,))["n"], 205)
check("...and the latest snapshot", db.one("SELECT snapshot FROM nx_servers WHERE id=%s", (SID,))["snapshot"]["players"][0]["ping"],
      30 + seq["n"])
check("...and the event cursor", int(db.one("SELECT event_cursor FROM nx_servers WHERE id=%s", (SID,))["event_cursor"]),
      seq["ev"])

print("== website restart ==")
hub.reset_for_tests()
after = staff.get("/api/control/servers/%s/snapshot" % SID).json()
check("dashboard reloads the stored snapshot after a restart", after["snapshot"]["players"][0]["name"], "Kaiii")
check("game server keeps syncing with the same key", sync(events=1).status_code, 200)

server.should_exit = True
print()
print("%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
