"""Advanced per-signal actions (Detectors page): risk -> log -> kick -> ban
must save. Real website process + real Postgres; the game server is
simulated with the exact bridge calls the resource makes.

    python tests/punishcheck.py      (DATABASE_URL, or an embedded `pgserver`)
"""
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if not os.environ.get("DATABASE_URL"):
    import pgserver  # noqa: E402
    _pg = pgserver.get_server(tempfile.mkdtemp(prefix="nxpun-"), cleanup_mode="stop")
    os.environ["DATABASE_URL"] = _pg.get_uri()
PORT = 38119
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
    print(("  PASS  " if ok else "  FAIL  ") + "%-62s %s" % (label, got if ok else "got %r wanted %r" % (got, want)))


db.run_migrations()
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
threading.Thread(target=server.run, daemon=True).start()
while not server.started:
    time.sleep(0.05)

stamp = int(time.time())
staff = httpx.Client(base_url=SITE, timeout=40, headers={"Origin": SITE})
staff.post("/api/control/auth/register", json={"email": "pun%d@nexusac.test" % stamp,
                                                "password": "correct-horse-battery-9", "name": "Owner"})
created = staff.post("/api/control/servers", json={"name": "Kai RP"}).json()
SID, TOKEN = created["id"], created["token"]
game = httpx.Client(base_url=SITE + "/api/control/bridge", timeout=40, headers={"Authorization": "Bearer " + TOKEN})

# What the resource reports: 203 signal kinds, each with its current action.
KINDS = {"kind%03d" % i: "risk" for i in range(202)}
KINDS["noclip"] = "risk"
state = {"seq": 0, "revision": 1, "acks": []}


def sync():
    state["seq"] += 1
    snap = {"overview": {"mode": "enforce", "version": "0.2.0", "uptime": 60, "online": 1},
            "players": [], "protections": [{"id": "NX-NOCLIP-001", "name": "Anti Noclip"}],
            "config": {"settings": {}, "kinds": [{"kind": k, "weight": 40, "action": a, "label": k}
                                                 for k, a in KINDS.items()],
                       "persistence": {"revision": state["revision"], "verified": True, "dirty": False}}}
    body = {"protocol": 1, "boot": "boot-1", "sequence": state["seq"], "sentAt": int(time.time()),
            "snapshot": snap, "acknowledgements": list(state["acks"])}
    state["acks"].clear()
    r = game.post("/sync", json=body)
    return r


def game_runs(commands):
    """What sv_panel.lua's Nx.webExecute does for `punish`, then the ack."""
    for c in commands:
        if c.get("type") != "punish":
            continue
        if KINDS.get(c["signal"]) != c["expected"]:
            state["acks"].append({"id": c["id"], "ok": False, "message": "That punishment changed."})
            continue
        KINDS[c["signal"]] = c["action"]
        state["revision"] += 1
        state["acks"].append({"id": c["id"], "ok": True, "message": "%s set to %s" % (c["signal"], c["action"])})


r = sync()
check("first sync with 203 signal kinds accepted", r.status_code, 200)
page = staff.get("/api/control/servers/%s/snapshot" % SID).json()
check("dashboard lists 203 signals", len(page["snapshot"]["config"]["kinds"]), 203)

hub.LONG_POLL_SECONDS = 3
for action in ("log", "kick", "ban", "risk"):
    expected = KINDS["noclip"]
    got = {}
    waiter = threading.Thread(target=lambda: got.setdefault("r", game.post("/wait", json={"protocol": 1})))
    waiter.start()
    time.sleep(0.3)
    q = staff.post("/api/control/servers/%s/commands" % SID,
                   json={"type": "punish", "signal": "noclip", "action": action, "expected": expected})
    check("%s: website accepted the change" % action, q.status_code, 202)
    if q.status_code != 202:
        print("        ->", q.text[:300])
        waiter.join(5)
        continue
    waiter.join(10)
    commands = got["r"].json().get("commands", []) if "r" in got else []
    check("%s: delivered to the game server" % action, [c.get("action") for c in commands], [action])
    game_runs(commands)
    check("%s: game server sync with the ack accepted" % action, sync().status_code, 200)
    snap = staff.get("/api/control/servers/%s/snapshot" % SID).json()
    row = next((k for k in snap["snapshot"]["config"]["kinds"] if k["kind"] == "noclip"), {})
    cmd = next((c for c in (snap["commands"] or []) if c["id"] == q.json()["id"]), {})
    check("%s: dashboard shows the new action" % action, row.get("action"), action)
    check("%s: command marked succeeded" % action, cmd.get("status"), "succeeded")

server.should_exit = True
print()
print("%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
