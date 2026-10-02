"""The dashboard snapshot only sends what changed, and responses are gzipped.

Render's free plan has 5 GB of outbound bandwidth a month; a dashboard that
re-downloaded the full snapshot and 200 evidence records every second used it
up in an afternoon. Runs the real endpoint against a fake database.

    python tests/snapshotcheck.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for key in ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SECRET_KEY", "DATABASE_URL"):
    os.environ.setdefault(key, "http://test.invalid" if key.startswith("SUPABASE_URL") else "test")

from fastapi.testclient import TestClient  # noqa: E402

from app import api_routes, db  # noqa: E402
from app.main import app  # noqa: E402

state = {"last_seen": 1000, "sequence": 5, "evidence_v": "abc", "media": 2, "snapshot_reads": 0, "evidence_reads": 0}
BIG = {"players": [{"src": i, "name": "P%d" % i, "network": "1.2.3.%d" % i} for i in range(60)],
       "protections": [{"id": "NX-%03d" % i, "info": "x" * 200} for i in range(60)]}


def fake_one(sql, args=()):
    if "FROM nx_servers" in sql and "snapshot" not in sql.split("FROM")[0]:
        return {"id": "s1", "name": "Test", "token_hint": "ab12", "last_seen": state["last_seen"],
                "sequence": state["sequence"]}
    if "md5(" in sql:
        return {"v": state["evidence_v"], "media": state["media"]}
    if "SELECT snapshot" in sql:
        state["snapshot_reads"] += 1
        return {"snapshot": BIG}
    raise AssertionError(sql)


def fake_query(sql, args=()):
    if "FROM nx_evidence" in sql:
        state["evidence_reads"] += 1
        return [{"id": i, "body": {"id": "E%d" % i, "at": i, "detail": "y" * 2000}, "images": 1} for i in range(200)]
    if "FROM nx_commands" in sql:
        return []
    raise AssertionError(sql)


db.one, db.query = fake_one, fake_query
api_routes.db.one, api_routes.db.query = fake_one, fake_query
api_routes.authenticated = lambda request: {"workspace": "w1", "role": "owner", "user_id": "u1"}

client = TestClient(app)
passed = failed = 0


def check(label, got, want):
    global passed, failed
    ok = got == want
    passed, failed = passed + ok, failed + (not ok)
    print(("  PASS  " if ok else "  FAIL  ") + "%-64s %s" % (label, got if ok else "got %r wanted %r" % (got, want)))


first = client.get("/api/control/servers/s1/snapshot")
d1 = first.json()
check("first load: full snapshot", len(d1["snapshot"]["players"]), 60)
check("...and full evidence", len(d1["evidence"]), 200)
check("...gzipped (browser asks for it)", first.headers.get("content-encoding"), "gzip")
full_bytes = len(json.dumps(d1))

q = "?sv=%s&ev=%s" % (d1["snapshotVersion"], d1["evidenceVersion"])
reads = dict(state)
second = client.get("/api/control/servers/s1/snapshot" + q)
d2 = second.json()
check("unchanged poll: snapshot not sent", d2["snapshot"], None)
check("...evidence not sent", d2["evidence"], None)
check("...flags say so", (d2["snapshotUnchanged"], d2["evidenceUnchanged"]), (True, True))
check("...the snapshot was not even read from the database", state["snapshot_reads"], reads["snapshot_reads"])
check("...nor the 200 evidence bodies", state["evidence_reads"], reads["evidence_reads"])
small = len(json.dumps(d2))
check("...under 1% of a full response", small * 100 < full_bytes, True)
print("        full %d bytes, unchanged %d bytes" % (full_bytes, small))

state["last_seen"] = 1030                       # the game server synced
d3 = client.get("/api/control/servers/s1/snapshot" + q).json()
check("after a sync: snapshot resent", d3["snapshot"] is not None, True)
check("...evidence still not (it did not change)", d3["evidence"], None)

state["media"] = 3                              # a screenshot arrived for a case
d4 = client.get("/api/control/servers/s1/snapshot?sv=%s&ev=%s" % (d3["snapshotVersion"], d1["evidenceVersion"])).json()
check("a new screenshot changes the evidence version: evidence resent", d4["evidence"] is not None, True)

print("%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
