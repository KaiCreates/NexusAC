"""The dashboard snapshot only sends what changed, and responses are gzipped.

Render's free plan has 5 GB of outbound bandwidth a month; a dashboard that
re-downloaded the full snapshot and 200 evidence records every second used it
up in an afternoon. Since the move to Neon (scale-to-zero, 100 CU-hours a
month) an unchanged poll must not touch the database at all either: versions
live in memory (app/hub.py). Runs the real endpoint against a fake database.

    python tests/snapshotcheck.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "test")

from fastapi.testclient import TestClient  # noqa: E402

from app import api_routes, db, hub  # noqa: E402
from app.main import app  # noqa: E402

SID = "11111111-1111-1111-1111-111111111111"
state = {"reads": 0, "snapshot_reads": 0, "evidence_reads": 0}
BIG = {"players": [{"src": i, "name": "P%d" % i, "network": "1.2.3.%d" % i} for i in range(60)],
       "protections": [{"id": "NX-%03d" % i, "info": "x" * 200} for i in range(60)]}
ROW = {"id": SID, "workspace": "w1", "name": "Test", "token_hash": "h", "token_hint": "ab12", "created": 1,
       "last_seen": 10**10, "boot": "b", "sequence": 5, "identity_cursor": 0, "event_cursor": 0,
       "event_boot": None, "punish_cursor": 0, "punish_boot": None}


def fake_one(sql, args=()):
    state["reads"] += 1
    if sql.startswith("SELECT id, workspace, name, token_hash"):
        return dict(ROW)
    if sql.startswith("SELECT snapshot FROM nx_servers"):
        state["snapshot_reads"] += 1
        return {"snapshot": BIG}
    raise AssertionError(sql)


def fake_query(sql, args=()):
    state["reads"] += 1
    if "FROM nx_evidence" in sql:
        state["evidence_reads"] += 1
        return [{"id": i, "body": {"id": "E%d" % i, "at": i, "detail": "y" * 2000}, "images": 1} for i in range(200)]
    if "FROM nx_commands" in sql:
        return []
    raise AssertionError(sql)


for mod in (db, api_routes.db, hub.db):
    mod.one, mod.query = fake_one, fake_query
api_routes.authenticated = lambda request: {"workspace": "w1", "role": "owner", "user_id": "u1"}

client = TestClient(app)
passed = failed = 0


def check(label, got, want):
    global passed, failed
    ok = got == want
    passed, failed = passed + ok, failed + (not ok)
    print(("  PASS  " if ok else "  FAIL  ") + "%-64s %s" % (label, got if ok else "got %r wanted %r" % (got, want)))


def versions(d):
    return "?sv=%s&ev=%s&cv=%s" % (d["snapshotVersion"], d["evidenceVersion"], d["commandsVersion"])


first = client.get("/api/control/servers/%s/snapshot" % SID)
d1 = first.json()
check("first load: full snapshot", len(d1["snapshot"]["players"]), 60)
check("...and full evidence", len(d1["evidence"]), 200)
check("...gzipped (browser asks for it)", first.headers.get("content-encoding"), "gzip")
full_bytes = len(json.dumps(d1))

reads = dict(state)
d2 = client.get("/api/control/servers/%s/snapshot%s" % (SID, versions(d1))).json()
check("unchanged poll: snapshot not sent", d2["snapshot"], None)
check("...evidence not sent", d2["evidence"], None)
check("...commands not sent", d2["commands"], None)
check("...flags say so", (d2["snapshotUnchanged"], d2["evidenceUnchanged"], d2["commandsUnchanged"]), (True, True, True))
check("...the database was not touched at all", state["reads"], reads["reads"])
small = len(json.dumps(d2))
check("...under 1% of a full response", small * 100 < full_bytes, True)
print("        full %d bytes, unchanged %d bytes" % (full_bytes, small))

live = hub.by_id(SID)
live.snapshot = {**BIG, "players": BIG["players"][:59]}   # the game server synced
live.version += 1
d3 = client.get("/api/control/servers/%s/snapshot%s" % (SID, versions(d2))).json()
check("after a sync: snapshot resent (from memory)", len(d3["snapshot"]["players"]), 59)
check("...evidence still not (it did not change)", d3["evidence"], None)
check("...still no snapshot read from the database", state["snapshot_reads"], reads["snapshot_reads"])

live.evidence_version += 1                                 # a screenshot arrived for a case
d4 = client.get("/api/control/servers/%s/snapshot%s" % (SID, versions(d3))).json()
check("a new screenshot changes the evidence version: evidence resent", d4["evidence"] is not None, True)

print("%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
