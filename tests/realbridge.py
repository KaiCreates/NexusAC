"""Run the REAL server/sv_web.lua against the running website.

Everything sv_web.lua touches is stubbed except its own logic: PerformHttpRequest
really posts to the site over HTTP, LoadResourceFile/SaveResourceFile really read
and write a receipt file, and the command it receives is really executed through
a stubbed Nx.webExecute. Proves the wiring end to end, not a Python imitation of it.
"""
import io, json, os, pathlib, sys, time
import httpx
import lupa

SITE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3001"
# Defaults to the NexusAC resource folder sitting beside this project.
RESOURCE = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else (
    pathlib.Path(__file__).resolve().parent.parent.parent / "NexusAC")

passed, failed = [], []
def check(name, ok, detail=""):
    (passed if ok else failed).append(name)
    print(("  PASS  " if ok else "  FAIL  ") + name + (("  -> " + str(detail)[:200]) if detail and not ok else ""))

# --------------------------------------------------------- provision an account
email = "lua+%d@nexusac.test" % int(time.time())
site = httpx.Client(base_url=SITE, timeout=40, headers={"Origin": SITE})
r = site.post("/api/control/auth/register",
              json={"email": email, "password": "correct-horse-battery-staple-9", "name": "Kai"})
check("account created for the test", r.status_code == 200, r.text)
r = site.post("/api/control/servers", json={"name": "Lua bridge test"})
check("api key issued", r.status_code == 201, r.text)
TOKEN, SERVER_ID = r.json()["token"], r.json()["id"]

# --------------------------------------------------------------- the Lua runtime
L = lupa.LuaRuntime(unpack_returned_tuples=True)
G = L.globals()

receipt_store = {}
executed = []
http_calls = []


def perform_http_request(url, cb, method="GET", body="", headers=None, opts=None):
    hdrs = dict(headers) if headers is not None else {}
    http_calls.append((method, url))
    try:
        response = httpx.post(url, content=body, headers=hdrs, timeout=40)
        cb(response.status_code, response.text, L.table())
    except Exception as error:
        cb(0, str(error), L.table())


def load_resource_file(resource, name):
    return receipt_store.get(name)


def save_resource_file(resource, name, data, length):
    receipt_store[name] = data
    return True


class Stop(Exception):
    pass


state = {"cycles": 0, "queued": None}


def wait(ms):
    """sv_web.lua's poll loop never ends, so the harness drives it from here.

    The whole file is executed ONCE and the loop is allowed to turn several
    times: `pending` (the acknowledgement buffer) is a local in that chunk, so
    re-executing the file per poll would silently discard it.
    """
    if not ms or ms < 2000:
        return  # the 100ms in-flight wait
    state["cycles"] += 1
    # cycle 1 is sv_web.lua's opening Wait(2000), before any sync has happened.
    # The website refuses commands to an offline server, so queue after sync #1.
    if state["cycles"] == 2:
        # Between poll 1 and poll 2, staff press Kick on the website.
        r = site.post("/api/control/servers/%s/commands" % SERVER_ID,
                      json={"type": "kick", "target": 7, "session": SESSION_KEY,
                            "reason": "Round trip through the real Lua"})
        check("website queued a kick", r.status_code == 202, r.text)
        state["queued"] = r.json().get("id")
    if state["cycles"] >= 5:
        raise Stop()


G.GetConvar = lambda name, default="": {
    "nexus_web_url": SITE, "nexus_web_token": TOKEN}.get(name, default)
G.PerformHttpRequest = perform_http_request
G.LoadResourceFile = load_resource_file
G.SaveResourceFile = save_resource_file
G.GetGameTimer = lambda: int(time.time() * 1000) % 10_000_000
G.Wait = wait
G.CreateThread = lambda fn: fn()
G.GetResourceState = lambda name: "started"

L.execute("json = { encode = nil, decode = nil }")
G.json.encode = lambda value: json.dumps(_to_py(value))
G.json.decode = lambda text: _to_lua(json.loads(text))


def _to_py(value):
    if lupa.lua_type(value) != "table":
        return value
    keys = list(value.keys())
    if keys and all(isinstance(k, int) for k in keys) and sorted(keys) == list(range(1, len(keys) + 1)):
        return [_to_py(value[k]) for k in sorted(keys)]
    return {str(k): _to_py(v) for k, v in value.items()}


def _to_lua(value):
    if isinstance(value, dict):
        table = L.table()
        for k, v in value.items():
            table[k] = _to_lua(v)
        return table
    if isinstance(value, list):
        table = L.table()
        for i, v in enumerate(value, 1):
            table[i] = _to_lua(v)
        return table
    return value


SESSION_KEY = "sess-lua-7"
SNAPSHOT = {
    "overview": {"mode": "enforce", "version": "1.4.0", "uptime": 900, "online": 1,
                 "watched": 0, "scored": 1, "clientless": 0,
                 "thresholds": {"flag": 40, "kick": 110, "ban": 160}},
    "players": [{"src": 7, "name": "LuaTester", "risk": 45, "ping": 30, "frozen": False,
                 "sessionKey": SESSION_KEY, "lifecycle": "NORMAL", "live": True}],
    "detectors": [{"id": "NX-NOCLIP-001", "name": "Noclip", "maturity": "OBSERVE",
                   "mode": "observe", "locked": False}],
    "bans": [], "feed": [], "logs": [],
    "config": {"settings": {}, "profile": "default"},
    "events": {}, "integrations": {"screenshots": "started", "webhooks": []},
    "evidence": [],
}

G.Nx = _to_lua({"RESOURCE": "NexusAC"})
G.Nx.webSnapshot = lambda: _to_lua(SNAPSHOT)
G.Nx.Evidence = _to_lua({})
G.Nx.Evidence.List = lambda filt: L.table()
G.Nx.Evidence.Get = lambda ident: None
G.Nx.audit = lambda src, action, detail: None


def web_execute(command):
    executed.append(_to_py(command))
    return True, "Player kicked by website staff."


G.Nx.webExecute = web_execute

print("\n== real sv_web.lua ==")
source = io.open(RESOURCE / "server" / "sv_web.lua", encoding="utf-8").read()
try:
    L.execute(source)
except Stop:
    pass
except lupa.LuaError as error:
    check("sv_web.lua runs", False, str(error)[:400])

check("sv_web.lua accepted the URL and key", bool(http_calls), http_calls)
check("it posted to the sync endpoint",
      any(url.endswith("/api/control/bridge/sync") for _, url in http_calls), http_calls)

r = site.get("/api/control/servers/%s/snapshot" % SERVER_ID)
view = r.json()
check("website shows the server online", view.get("online") is True, view.get("lastSeen"))
check("the real snapshot rendered", (view.get("snapshot") or {}).get("players", [{}])[0].get("name") == "LuaTester",
      view.get("snapshot"))

# The command was queued from inside wait() between poll 1 and poll 2, so the
# whole round trip happened during the single chunk execution above.
print("\n== command round trip ==")
command_id = state["queued"]

check("sv_web.lua executed the command", len(executed) == 1 and executed[0]["type"] == "kick", executed)
check("command carried the reason", executed and executed[0].get("reason") == "Round trip through the real Lua", executed)
check("a receipt was persisted", "data/web_commands.json" in receipt_store, list(receipt_store))
receipts = json.loads(receipt_store.get("data/web_commands.json", "{}"))
check("receipt records success", receipts.get(command_id, {}).get("ok") is True, receipts)

check("command executed exactly once across polls", len(executed) == 1, executed)

r = site.get("/api/control/workspace")
recorded = next((c for c in r.json()["commands"] if c["id"] == command_id), None)
check("website recorded the acknowledgement",
      recorded and recorded["status"] == "succeeded", recorded)
check("website stored the Lua result message",
      recorded and "kicked" in (recorded.get("result") or "").lower(), recorded)

print("\n%d passed, %d failed" % (len(passed), len(failed)))
if failed:
    print("FAILED: " + ", ".join(failed))
sys.exit(1 if failed else 0)
