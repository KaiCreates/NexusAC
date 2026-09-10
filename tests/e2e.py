"""End-to-end test of the NexusAC website, driving it exactly the way
server/sv_web.lua does."""
import base64, json, sys, time, uuid
import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3001"
EMAIL = "kai+%d@nexusac.test" % int(time.time())
PASSWORD = "correct-horse-battery-staple-9"

passed, failed = [], []


def check(name, condition, detail=""):
    (passed if condition else failed).append(name)
    print(("  PASS  " if condition else "  FAIL  ") + name + (("  -> " + str(detail)[:220]) if detail and not condition else ""))


site = httpx.Client(base_url=BASE, timeout=40, headers={"Origin": BASE})
bridge = httpx.Client(base_url=BASE, timeout=40)

print("\n== accounts ==")
r = site.post("/api/control/auth/register", json={"email": EMAIL, "password": PASSWORD, "name": "Kai"})
check("register creates an account", r.status_code == 200, r.text)
check("session cookie set", "nexus_session" in site.cookies, dict(site.cookies))

r = site.post("/api/control/auth/register", json={"email": EMAIL, "password": PASSWORD, "name": "Kai"})
check("duplicate register refused", r.status_code == 409, r.text)

r = site.post("/api/control/auth/login", json={"email": EMAIL, "password": "wrong-password-here"})
check("bad password refused", r.status_code == 401, r.text)

r = site.post("/api/control/auth/login", json={"email": EMAIL, "password": PASSWORD})
check("login works", r.status_code == 200, r.text)

r = site.post("/api/control/auth/register", json={"email": "x@y.co", "password": "short"})
check("short password refused", r.status_code == 400, r.text)

r = site.get("/api/control/workspace")
check("workspace loads", r.status_code == 200, r.text)
work = r.json()
check("owner role assigned", work["user"]["role"] == "owner", work["user"])

print("\n== api keys ==")
r = site.post("/api/control/servers", json={"name": "Trinidad RP"})
check("server created", r.status_code == 201, r.text)
server = r.json()
TOKEN, SERVER_ID = server["token"], server["id"]
check("key is 43 url-safe chars (sv_web.lua requires exactly this)",
      len(TOKEN) == 43 and all(c.isalnum() or c in "-_" for c in TOKEN), TOKEN)

r = bridge.post("/api/control/bridge/sync", json={}, headers={"Authorization": "Bearer " + "x" * 43})
check("unknown key rejected", r.status_code == 401, r.text)
r = bridge.post("/api/control/bridge/sync", json={})
check("missing key rejected", r.status_code == 401, r.text)

print("\n== bridge sync ==")
BOOT = "%x-%x-%x-%x" % (int(time.time()), 12345, 6789, 4242)
AUTH = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}
SESSION_KEY = "sess-abc-123"


def snapshot(players=1, evidence_id=None):
    ev = []
    if evidence_id:
        ev = [{"id": evidence_id, "resourceId": "NX-E-0001", "at": int(time.time()),
               "detection": "Godmode", "detector": "NX-GODMODE-001", "confidence": 85,
               "action": "ban", "player": {"name": "Suspect", "src": 3},
               "detail": {"families": ["damage", "invincible"]},
               "signals": [{"kind": "godmode", "weight": 60, "detail": "damage+invincible"}],
               "screenshot": {"status": "captured"}}]
    return {
        "overview": {"mode": "enforce", "version": "1.4.0", "uptime": 3600, "online": players,
                     "watched": 1, "scored": 1, "clientless": 0,
                     "entities": {"created": 40, "denied": 2},
                     "thresholds": {"flag": 40, "kick": 110, "ban": 160},
                     "registry": {"models": 7190, "vehicles": 900, "peds": 700, "weapons": 100}},
        "players": [{"src": 3, "name": "Suspect", "risk": 55, "ping": 42, "frozen": False,
                     "sessionKey": SESSION_KEY, "lifecycle": "NORMAL", "ped": "a_m_y_hipster_01",
                     "health": 200, "armour": 0, "signals": 2, "live": True}][:players],
        "detectors": [{"id": "NX-CURSOR-001", "name": "Cursor interference", "maturity": "STABLE",
                       "mode": "enforce", "locked": True, "enforcement": "risk signal (+30)",
                       "stats": {"rounds": 10, "clean": 9}},
                      {"id": "NX-NOCLIP-001", "name": "Noclip", "maturity": "OBSERVE",
                       "mode": "observe", "locked": False, "enforcement": "risk signal (+45)"}],
        "bans": [{"banId": "B1", "identifier": "license:abc123", "name": "Cheater",
                  "reason": "Godmode", "at": int(time.time()) - 500, "expires": 0,
                  "evidence": "NX-E-0001"}],
        "feed": [{"at": int(time.time()), "src": 3, "name": "Suspect", "stream": "signal",
                  "kind": "godmode", "weight": 55, "detail": "modifier 0.0", "risk": 55}],
        "logs": [{"at": int(time.time()), "category": "detections", "title": "Godmode incident",
                  "player": "Suspect", "group": "detection"}],
        "config": {"settings": {"Mode": {"value": "enforce", "kind": "enum", "live": True,
                                         "values": {"observe": True, "enforce": True}},
                                "Cursor.holdRatio": {"value": 0.65, "kind": "number", "live": True,
                                                     "lo": 0, "hi": 1},
                                "Entity.enabled": {"value": True, "kind": "boolean", "live": True}},
                   "profile": "default"},
        "events": {},
        "integrations": {"screenshots": "started",
                         "webhooks": [{"category": "detections", "configured": True,
                                       "status": "healthy", "sent": 12, "failed": 0}]},
        "evidence": ev,
    }


def sync(sequence, boot=BOOT, acks=None, evidence_id=None, sent_at=None):
    return bridge.post("/api/control/bridge/sync", headers=AUTH, content=json.dumps({
        "protocol": 1, "boot": boot, "sequence": sequence,
        "sentAt": sent_at if sent_at is not None else int(time.time()),
        "snapshot": snapshot(evidence_id=evidence_id),
        "acknowledgements": acks if acks is not None else {},  # FiveM sends {} for an empty list
    }))


r = sync(1)
check("first sync accepted", r.status_code == 200, r.text)
body = r.json()
check("response shape matches sv_web.lua expectations",
      body.get("protocol") == 1 and body.get("accepted") == 1 and body.get("commands") == [], body)

r = sync(1)
check("replayed sequence refused", r.status_code == 409, r.text)
r = sync(2)
check("next sequence accepted", r.status_code == 200, r.text)

r = sync(3, boot="retired-boot-value")
check("new boot accepted", r.status_code == 200, r.text)
r = sync(4, boot=BOOT)
check("returning to a retired boot refused", r.status_code == 409, r.text)

r = sync(5, boot="retired-boot-value", sent_at=int(time.time()) - 400)
check("clock skew refused", r.status_code == 400, r.text)

r = bridge.post("/api/control/bridge/sync", headers=AUTH,
                content=json.dumps({"protocol": 1, "boot": "b", "sequence": 6,
                                    "sentAt": int(time.time()),
                                    "snapshot": {"overview": {"mode": "nonsense", "version": "1",
                                                              "uptime": 1, "online": 1}},
                                    "acknowledgements": []}))
check("invalid snapshot refused", r.status_code == 400, r.text)

print("\n== live view ==")
r = site.get("/api/control/servers/%s/snapshot" % SERVER_ID)
check("snapshot endpoint works", r.status_code == 200, r.text)
view = r.json()
check("server shows online", view["online"] is True, view.get("lastSeen"))
check("players came through", len(view["snapshot"]["players"]) == 1, view["snapshot"]["players"])
check("detectors came through", len(view["snapshot"]["detectors"]) == 2, "")
check("config settings came through", "Cursor.holdRatio" in view["snapshot"]["config"]["settings"], "")

print("\n== commands ==")
BOOT2 = "retired-boot-value"
r = site.post("/api/control/servers/%s/commands" % SERVER_ID,
              json={"type": "kick", "target": 3, "session": SESSION_KEY, "reason": "Testing the bridge"})
check("kick queued", r.status_code == 202, r.text)
command_id = r.json()["id"]

r = site.post("/api/control/servers/%s/commands" % SERVER_ID,
              json={"type": "kick", "target": 3, "session": "stale-session", "reason": "Should fail"})
check("stale session refused", r.status_code == 409, r.text)

r = site.post("/api/control/servers/%s/commands" % SERVER_ID,
              json={"type": "setting", "path": "Cursor.holdRatio", "value": 0.8, "expected": 0.1})
check("wrong expected value refused", r.status_code == 409, r.text)

r = site.post("/api/control/servers/%s/commands" % SERVER_ID,
              json={"type": "detector", "detector": "NX-CURSOR-001", "mode": "disabled", "expected": "enforce"})
check("locked detector refused", r.status_code == 409, r.text)

r = sync(6, boot=BOOT2)
check("sync delivers the queued command", r.status_code == 200 and len(r.json()["commands"]) == 1, r.text[:300])
delivered = r.json()["commands"][0]
check("command id is 36 chars (sv_web.lua checks this)", len(delivered["id"]) == 36, delivered["id"])
check("command carries expires + actor",
      isinstance(delivered.get("expires"), int) and delivered.get("actor") == "Kai", delivered)
check("command body intact", delivered["type"] == "kick" and delivered["target"] == 3, delivered)

r = sync(7, boot=BOOT2)
check("command not delivered twice", len(r.json()["commands"]) == 1
      and r.json()["commands"][0]["id"] == delivered["id"], "still 'sent' until acked - correct")

r = sync(8, boot=BOOT2, acks=[{"id": command_id, "ok": True, "message": "Player kicked."}])
check("acknowledgement clears the queue", len(r.json()["commands"]) == 0, r.text[:200])

r = site.get("/api/control/workspace")
state = r.json()
recorded = next((c for c in state["commands"] if c["id"] == command_id), None)
check("command recorded as succeeded", recorded and recorded["status"] == "succeeded", recorded)
check("audit log written", any(a["action"] == "command.kick" for a in state["audit"]), "")

print("\n== evidence + screenshots ==")
EVIDENCE_ID = BOOT2 + ":NX-E-0001"
r = sync(9, boot=BOOT2, evidence_id=EVIDENCE_ID)
check("evidence accepted", r.status_code == 200, r.text[:200])

jpeg = base64.b64encode(bytes.fromhex("ffd8ff") + b"\x00" * 600).decode()
r = bridge.post("/api/control/bridge/media", headers=AUTH,
                json={"evidenceId": EVIDENCE_ID, "slot": 0, "data": "data:image/jpeg;base64," + jpeg})
check("screenshot accepted", r.status_code == 200, r.text)

r = bridge.post("/api/control/bridge/media", headers=AUTH,
                json={"evidenceId": "unknown:case", "slot": 0, "data": "data:image/jpeg;base64," + jpeg})
check("screenshot without evidence refused", r.status_code == 409, r.text)

notjpeg = base64.b64encode(b"\x89PNG" + b"\x00" * 600).decode()
r = bridge.post("/api/control/bridge/media", headers=AUTH,
                json={"evidenceId": EVIDENCE_ID, "slot": 1, "data": "data:image/jpeg;base64," + notjpeg})
check("non-JPEG refused", r.status_code == 400, r.text)

r = site.get("/api/control/servers/%s/snapshot" % SERVER_ID)
cases = r.json()["evidence"]
check("evidence reaches the dashboard", len(cases) == 1 and cases[0]["images"] == 1, cases)

r = site.get("/api/control/servers/%s/media/%s/0" % (SERVER_ID, EVIDENCE_ID))
check("screenshot downloads as jpeg",
      r.status_code == 200 and r.headers["content-type"] == "image/jpeg", r.status_code)

print("\n== isolation ==")
other = httpx.Client(base_url=BASE, timeout=40, headers={"Origin": BASE})
r = other.post("/api/control/auth/register",
               json={"email": "other+%d@nexusac.test" % int(time.time()), "password": PASSWORD, "name": "Other"})
check("second account created", r.status_code == 200, r.text)
r = other.get("/api/control/servers/%s/snapshot" % SERVER_ID)
check("another workspace cannot read the server", r.status_code == 404, r.status_code)
r = other.post("/api/control/servers/%s/commands" % SERVER_ID,
               json={"type": "kick", "target": 3, "session": SESSION_KEY, "reason": "Should not work"})
check("another workspace cannot command the server", r.status_code == 404, r.status_code)

anon = httpx.Client(base_url=BASE, timeout=40, headers={"Origin": BASE})
r = anon.get("/api/control/workspace")
check("signed-out access refused", r.status_code == 401, r.status_code)

r = site.post("/api/control/servers", json={"name": "CSRF"}, headers={"Origin": "https://evil.example"})
check("cross-origin POST refused", r.status_code == 403, r.status_code)

print("\n== key rotation ==")
r = site.post("/api/control/servers/%s/rotate" % SERVER_ID, json={})
check("key rotated", r.status_code == 200, r.text)
NEW = r.json()["token"]
check("rotated key differs", NEW != TOKEN, "")
r = sync(10, boot=BOOT2)
check("old key stops working", r.status_code == 401, r.status_code)
AUTH["Authorization"] = "Bearer " + NEW
r = sync(1, boot="fresh-boot-after-rotate")
check("new key works and sequence resets", r.status_code == 200, r.text[:200])

print("\n== pages ==")
# Signed-out pages are checked with the anonymous client: a signed-in visitor is
# deliberately redirected off /, /login and /register to the dashboard.
for path, needle in [("/", "Protection that"), ("/login", "Sign in"), ("/register", "Create account"),
                     ("/docs", "nexus_web_token")]:
    r = anon.get(path)
    check("page %s renders" % path, r.status_code == 200 and needle in r.text, r.status_code)
for path, needle in [("/dashboard", "Workspace"), ("/dashboard/servers/" + SERVER_ID, "Live")]:
    r = site.get(path)
    check("page %s renders" % path, r.status_code == 200 and needle in r.text, r.status_code)
for path in ("/", "/login", "/register"):
    r = site.get(path)
    check("signed-in visitor redirected off %s" % path, r.status_code == 303, r.status_code)

print("\n%d passed, %d failed" % (len(passed), len(failed)))
if failed:
    print("FAILED: " + ", ".join(failed))
sys.exit(1 if failed else 0)
