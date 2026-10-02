"""Live change speed, end to end, with the REAL game-server bridge.

Runs NexusAC's actual server/sv_web.lua (via lupa) against a real website
process and a real Postgres, in real time, with real HTTP. Then a staff member
toggles detectors on the dashboard API and we time click -> applied on the game
server -> "succeeded" visible to the dashboard. The bar is 2 seconds.

    python tests/livespeedcheck.py [path to NexusAC]
"""
import os
import sys
import tempfile
import threading
import time
import queue

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NEXUS = sys.argv[1] if len(sys.argv) > 1 else r'C:/Fxserver/txData/ESXLegacy_6123C7.base/resources/[nexus]/NexusAC'
if not os.environ.get("DATABASE_URL"):
    import pgserver  # noqa: E402
    _pg = pgserver.get_server(tempfile.mkdtemp(prefix="nxlive-"), cleanup_mode="stop")
    os.environ["DATABASE_URL"] = _pg.get_uri()
PORT = 38121
SITE = "http://127.0.0.1:%d" % PORT
os.environ["APP_URL"] = SITE

import httpx  # noqa: E402
import lupa  # noqa: E402
import uvicorn  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402

passed = failed = 0


def check(label, got, want=True):
    global passed, failed
    ok = got == want
    passed, failed = passed + ok, failed + (not ok)
    print(("  PASS  " if ok else "  FAIL  ") + "%-60s %s" % (label, got if ok else "got %r wanted %r" % (got, want)))


db.run_migrations()
web = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
threading.Thread(target=web.run, daemon=True).start()
while not web.started:
    time.sleep(0.05)

stamp = int(time.time())
staff = httpx.Client(base_url=SITE, timeout=40, headers={"Origin": SITE})
staff.post("/api/control/auth/register", json={"email": "live%d@nexusac.test" % stamp,
                                                "password": "correct-horse-battery-9", "name": "Owner"})
created = staff.post("/api/control/servers", json={"name": "Kai RP"}).json()
SID, TOKEN = created["id"], created["token"]

# ------------------------------------------------------------------ the game server
L = lupa.LuaRuntime(unpack_returned_tuples=True)
G = L.globals()
T0 = time.monotonic()
callbacks = queue.Queue()
GAME_HTTP = httpx.Client(timeout=40, limits=httpx.Limits(max_connections=8))
applied = {}
modes = {"NX-NOCLIP-001": "enforce", "NX-FCAM-001": "enforce", "NX-RAG-001": "enforce"}
revision = {"n": 1}


def http(url, cb, method, body, headers, options):
    hdrs = {k: v for k, v in (headers or {}).items()}
    def run():
        try:
            # One pooled client, like FiveM's native HTTP (a fresh httpx client
            # per request costs ~0.5 s on Windows loading the CA bundle).
            r = GAME_HTTP.request(method or "GET", url, content=body, headers=hdrs)
            callbacks.put((cb, r.status_code, r.text))
        except Exception:
            callbacks.put((cb, 0, ""))
    threading.Thread(target=run, daemon=True).start()


def web_execute(command):
    kind = command["type"]
    if kind == "detector":
        if modes.get(command["detector"]) != command["expected"]:
            return False, "changed"
        modes[command["detector"]] = command["mode"]
        revision["n"] += 1
        applied[command["id"]] = time.monotonic()
        return True, "%s set to %s" % (command["detector"], command["mode"])
    return False, "unsupported in this test"


def snapshot(_include=None):
    return L.table_from({
        "overview": L.table_from({"mode": "enforce", "version": "0.2.0", "uptime": 60, "online": 1}),
        "players": L.table_from([]),
        "detectors": L.table_from([L.table_from({"id": k, "name": k, "mode": v}) for k, v in modes.items()]),
        "config": L.table_from({"settings": L.table_from({}),
                                "persistence": L.table_from({"revision": revision["n"], "verified": True, "dirty": False})}),
    })


L.execute("""
local py = ...
Nx = { RESOURCE = 'NexusAC', sessions = {} }
function Nx.Evidence_List() return {} end
Nx.Evidence = { List = function() return {} end, Get = function() return nil end }
local convars = py.convars
function GetConvar(k, d) local v = convars[k]; if v == nil then return d end; return v end
function GetConvarInt(k, d) local v = convars[k]; if v == nil then return d end; return math.tointeger(tonumber(v)) end
function GetGameTimer() return math.floor(py.now()) end
function LoadResourceFile() return nil end
function SaveResourceFile() return true end
function RegisterCommand() end
function TriggerClientEvent() end
function IsPlayerAceAllowed() return false end
function print(...) end
threads = {}
function CreateThread(fn) threads[#threads + 1] = { co = coroutine.create(fn), at = 0 } end
function SetTimeout(ms, fn) CreateThread(function() Wait(ms); fn() end) end
function Wait(ms) coroutine.yield(ms or 0) end
function PerformHttpRequest(url, cb, method, body, headers, options)
    py.http(url, cb, method, body, headers, options)
end
function Nx.webSnapshot() return py.snapshot() end
function Nx.webExecute(command)
    local plain = {}
    for k, v in pairs(command) do plain[k] = v end
    local ok, msg = py.execute(plain)
    return ok, msg
end
""", L.table_from({
    "convars": L.table_from({"nexus_web_url": SITE, "nexus_web_token": TOKEN, "nexus_web_sync_ms": "30000"}),
    "now": lambda: (time.monotonic() - T0) * 1000,
    "http": http,
    "snapshot": snapshot,
    "execute": lambda cmd: web_execute(dict(cmd.items())),
}))
# FiveM's json: real JSON both ways.
L.execute("""
local py = ...
json = { encode = function(t) return py.encode(t) end, decode = function(s) return py.decode(s) end }
""", L.table_from({
    "encode": lambda t: __import__("json").dumps(lua_to_py(t)),
    "decode": lambda s: py_to_lua(__import__("json").loads(s) if s else None),
}))


def lua_to_py(v):
    if lupa.lua_type(v) == "table":
        keys = list(v.keys())
        if keys and all(isinstance(k, int) for k in keys) and sorted(keys) == list(range(1, len(keys) + 1)):
            return [lua_to_py(v[k]) for k in sorted(keys)]
        if not keys:
            return {}
        return {str(k): lua_to_py(v[k]) for k in keys}
    return v


def py_to_lua(v):
    if isinstance(v, dict):
        return L.table_from({k: py_to_lua(x) for k, x in v.items()})
    if isinstance(v, list):
        return L.table_from([py_to_lua(x) for x in v])
    return v


with open(os.path.join(NEXUS, "server", "sv_web.lua"), encoding="utf-8") as fh:
    L.execute(fh.read())

running = {"on": True}


L.execute("""
function step(now)
    for _, th in ipairs(threads) do
        if th.at <= now and coroutine.status(th.co) ~= 'dead' then
            local ok, ms = coroutine.resume(th.co)
            if not ok then th.at = math.huge; lastError = tostring(ms) else th.at = now + (ms or 0) end
        end
    end
end
""")
step = G.step


def game_loop():
    while running["on"]:
        now = (time.monotonic() - T0) * 1000
        while not callbacks.empty():
            cb, status, text = callbacks.get()
            cb(status, text, L.table_from({}))
        step(now)
        if G.lastError:
            print("        game-side error:", G.lastError)
            G.lastError = None
        time.sleep(0.005)


threading.Thread(target=game_loop, daemon=True).start()

# ------------------------------------------------------------------ measure
deadline = time.time() + 20
while time.time() < deadline:
    page = staff.get("/api/control/servers/%s/snapshot" % SID).json()
    if page.get("online") and (page.get("link") or {}).get("instant"):
        break
    time.sleep(0.2)
check("game server connected through the real sv_web.lua", page.get("online"), True)
check("...and holding the instant channel (dashboard badge)", (page.get("link") or {}).get("instant"), True)
time.sleep(2)

times = []
for i, (det, mode) in enumerate([("NX-NOCLIP-001", "disabled"), ("NX-FCAM-001", "observe"),
                                 ("NX-RAG-001", "disabled"), ("NX-NOCLIP-001", "enforce")]):
    clicked = time.monotonic()
    q = staff.post("/api/control/servers/%s/commands" % SID,
                   json={"type": "detector", "detector": det, "mode": mode, "expected": modes[det]})
    if q.status_code != 202:
        check("%s accepted" % det, q.status_code, 202)
        continue
    cid = q.json()["id"]
    seen = None
    while time.monotonic() - clicked < 10:
        snap = staff.get("/api/control/servers/%s/snapshot" % SID).json()
        cmd = next((c for c in (snap.get("commands") or []) if c["id"] == cid), {})
        row = next((d for d in snap["snapshot"].get("detectors", []) if d["id"] == det), {})
        if cmd.get("status") == "succeeded" and row.get("mode") == mode:
            seen = time.monotonic()
            break
        time.sleep(0.1)
    applied_s = applied.get(cid, 0) - clicked if cid in applied else None
    total = (seen - clicked) if seen else None
    print("        %s -> %s: applied on the game server after %s, saved on the dashboard after %s" % (
        det, mode, "%.2fs" % applied_s if applied_s is not None else "never",
        "%.2fs" % total if total else "never"))
    check("%s -> %s saved within 2 s" % (det, mode), total is not None and total < 2.0, True)
    if total:
        times.append(total)
    time.sleep(1.5)

if times:
    print("        slowest %.2fs, average %.2fs (local network; add your internet round trips)" % (max(times), sum(times) / len(times)))
last = staff.get("/api/control/servers/%s/snapshot" % SID).json().get("link") or {}
check("dashboard reports the measured round trip", last.get("roundTripMs") is not None, True)

running["on"] = False
web.should_exit = True
print()
print("%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
