"""Render the website in a real browser with a real snapshot behind it, and
assert the pages actually show the data (not just return 200)."""
import json, sys, time, base64
import httpx
from playwright.sync_api import sync_playwright

SITE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3001"
OUT = r"C:/Users/Kai/AppData/Local/Temp/claude/C--Users-Kai/9a5a5504-a77f-49dd-839d-cb32703d3f55/scratchpad"
EMAIL = "ui+%d@nexusac.test" % int(time.time())
PASSWORD = "correct-horse-battery-staple-9"

passed, failed = [], []
def check(name, ok, detail=""):
    (passed if ok else failed).append(name)
    print(("  PASS  " if ok else "  FAIL  ") + name + (("  -> " + str(detail)[:200]) if detail and not ok else ""))

site = httpx.Client(base_url=SITE, timeout=40, headers={"Origin": SITE})
site.post("/api/control/auth/register", json={"email": EMAIL, "password": PASSWORD, "name": "Kai"})
r = site.post("/api/control/servers", json={"name": "Trinidad RP - main"})
TOKEN, SERVER_ID = r.json()["token"], r.json()["id"]

EV = "boot-ui:NX-E-9001"
snapshot = {
    "overview": {"mode": "enforce", "version": "1.4.0", "uptime": 48000, "online": 3,
                 "watched": 1, "scored": 2, "clientless": 1,
                 "entities": {"created": 812, "denied": 6},
                 "thresholds": {"flag": 40, "kick": 110, "ban": 160},
                 "registry": {"models": 7190, "vehicles": 901, "peds": 712, "weapons": 104},
                 "allowCount": 40},
    "players": [
        {"src": 3, "name": "Suspect", "risk": 165, "ping": 42, "frozen": False, "sessionKey": "k3",
         "lifecycle": "NORMAL", "ped": "a_m_y_hipster_01", "health": 200, "armour": 100,
         "signals": 4, "live": True},
        {"src": 5, "name": "Watched Guy", "risk": 55, "ping": 88, "frozen": True, "sessionKey": "k5",
         "lifecycle": "NORMAL", "ped": "mp_m_freemode_01", "health": 200, "armour": 0,
         "signals": 1, "live": True},
        {"src": 9, "name": "Normal Player", "risk": 0, "ping": 31, "frozen": False, "sessionKey": "k9",
         "lifecycle": "NORMAL", "ped": "mp_f_freemode_01", "health": 200, "armour": 0,
         "signals": 0, "live": False},
    ],
    "detectors": [
        {"id": "NX-CURSOR-001", "name": "Cursor interference", "maturity": "STABLE",
         "mode": "enforce", "locked": True, "enforcement": "risk signal (+55)",
         "stats": {"rounds": 214, "clean": 209, "held": 5}},
        {"id": "NX-GODMODE-001", "name": "Godmode", "maturity": "STABLE", "mode": "enforce",
         "locked": False, "enforcement": "incident", "stats": {"incidents": 2}},
        {"id": "NX-NOCLIP-001", "name": "Noclip", "maturity": "OBSERVE", "mode": "observe",
         "locked": False, "enforcement": "risk signal (+45)"},
        {"id": "NX-SILENT-001", "name": "Silent aim", "maturity": "BETA", "mode": "disabled",
         "locked": False, "enforcement": "risk signal (+50)"},
    ],
    "bans": [{"banId": "B1", "identifier": "license:9f2c8ab31", "name": "Cheater",
              "reason": "Godmode", "at": int(time.time()) - 7200, "expires": 0,
              "evidence": "NX-E-9001"}],
    "feed": [
        {"at": int(time.time()) - 30, "src": 3, "name": "Suspect", "stream": "signal",
         "kind": "godmode", "weight": 70, "detail": "damage+invincible, 85% confidence", "risk": 165},
        {"at": int(time.time()) - 90, "src": 5, "name": "Watched Guy", "stream": "signal",
         "kind": "teleport", "weight": 20, "detail": "148m in 0.6s window", "risk": 55},
        {"at": int(time.time()) - 140, "src": 0, "name": "server", "stream": "entity",
         "kind": "entity_denied", "weight": 0, "detail": "adder denied (vehicle/large) -- not allowlisted"},
    ],
    "logs": [{"at": int(time.time()) - 40, "category": "detections", "title": "Godmode incident opened",
              "player": "Suspect", "group": "detection"},
             {"at": int(time.time()) - 300, "category": "staff", "title": "Config change: Mode",
              "player": "Kai", "group": "audit"}],
    "config": {"settings": {
        "Mode": {"value": "enforce", "kind": "enum", "live": True,
                 "values": {"observe": True, "enforce": True}},
        "Cursor.holdRatio": {"value": 0.65, "kind": "number", "live": True, "lo": 0, "hi": 1},
        "Entity.enabled": {"value": True, "kind": "boolean", "live": True},
        "State.settleSec": {"value": 120, "kind": "number", "live": False, "lo": 0, "hi": 600},
    }, "profile": "default"},
    "events": {},
    "integrations": {"screenshots": "started",
                     "webhooks": [{"category": "detections", "configured": True,
                                   "status": "healthy", "sent": 148, "failed": 0},
                                  {"category": "bans", "configured": False,
                                   "status": "idle", "sent": 0, "failed": 0}]},
    "evidence": [{"id": EV, "resourceId": "NX-E-9001", "at": int(time.time()) - 60,
                  "detection": "Godmode", "detector": "NX-GODMODE-001", "confidence": 85,
                  "action": "ban", "player": {"name": "Suspect", "src": 3},
                  "detail": {"families": ["damage", "invincible"], "alive": 42},
                  "signals": [{"kind": "godmode", "weight": 70, "detail": "damage+invincible"}],
                  "screenshot": {"status": "captured"}}],
}

httpx.post(SITE + "/api/control/bridge/sync",
           headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
           content=json.dumps({"protocol": 1, "boot": "boot-ui", "sequence": 1,
                               "sentAt": int(time.time()), "snapshot": snapshot,
                               "acknowledgements": []}), timeout=40)
jpeg = base64.b64encode(bytes.fromhex("ffd8ff") + b"\x00" * 900).decode()
httpx.post(SITE + "/api/control/bridge/media",
           headers={"Authorization": "Bearer " + TOKEN},
           json={"evidenceId": EV, "slot": 0, "data": "data:image/jpeg;base64," + jpeg}, timeout=40)

errors = []
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1500, "height": 1000})
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))

    # The account already exists (the setup above created it through the API),
    # so this exercises the sign-in path.
    page.goto(SITE + "/login")
    page.fill("#email", EMAIL)
    page.fill("#password", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_url("**/dashboard", timeout=20000)
    page.wait_for_timeout(1500)
    check("dashboard reached after sign-in", "/dashboard" in page.url, page.url)
    check("server listed on the dashboard", page.locator("text=Trinidad RP - main").count() > 0)
    check("server card shows it reporting", page.locator(".server-cards .badge.success").count() > 0)
    page.screenshot(path=OUT + "/shot-dashboard.png", full_page=True)

    page.goto(SITE + "/dashboard/servers/" + SERVER_ID)
    page.wait_for_timeout(2000)
    check("console header shows the name",
          "Trinidad RP" in page.locator("#name").inner_text(), page.locator("#name").inner_text())
    stats = page.locator("#stats").inner_text()
    check("stat tiles populated", "Online" in stats and "enforce" in stats, stats[:160])
    page.screenshot(path=OUT + "/shot-overview.png", full_page=True)

    for name, needle in [("Players", "Suspect"), ("Detections", "godmode"),
                         ("Detectors", "NX-CURSOR-001"), ("Bans", "license:9f2c8ab31"),
                         ("Evidence", "Godmode"), ("Logs", "Godmode incident opened"),
                         ("Configuration", "Cursor.holdRatio")]:
        page.click(".sidebar-link[data-tab='%s']" % name)
        page.wait_for_timeout(500)
        body = page.locator("#view").inner_text()
        check("tab %s shows real data" % name, needle in body, body[:180])
        if name in ("Players", "Evidence", "Configuration"):
            page.screenshot(path=OUT + "/shot-%s.png" % name.lower(), full_page=True)

    # The high-risk player must be marked, and the clean one must not be.
    page.click(".sidebar-link[data-tab='Players']")
    page.wait_for_timeout(400)
    check("high-risk row flagged red", page.locator("#view tr.hot").count() == 1,
          page.locator("#view tr.hot").count())
    check("mid-risk row flagged amber", page.locator("#view tr.flag").count() == 1,
          page.locator("#view tr.flag").count())

    # Evidence drawer opens with the screenshot.
    page.click(".sidebar-link[data-tab='Evidence']")
    page.wait_for_timeout(400)
    page.click("[data-case='0']")
    page.wait_for_timeout(800)
    check("evidence drawer opens", page.locator("dialog.drawer[open]").count() == 1)
    check("screenshot rendered in the drawer", page.locator("dialog.drawer .evidence-preview img").count() == 1)
    page.screenshot(path=OUT + "/shot-evidence-drawer.png")
    page.keyboard.press("Escape")

    page.goto(SITE + "/docs")
    page.wait_for_timeout(400)
    check("docs page renders", "nexus_web_token" in page.content())
    page.screenshot(path=OUT + "/shot-docs.png", full_page=True)

    # Signed-out landing page.
    anon = browser.new_page(viewport={"width": 1500, "height": 1000})
    anon.goto(SITE + "/")
    anon.wait_for_timeout(400)
    check("landing page renders", "Protection that" in anon.content())
    anon.screenshot(path=OUT + "/shot-landing.png", full_page=True)

    browser.close()

real_errors = [e for e in errors if "favicon" not in e.lower()]
check("no javascript errors on any page", not real_errors, real_errors[:3])

print("\n%d passed, %d failed" % (len(passed), len(failed)))
if failed:
    print("FAILED: " + ", ".join(failed))
sys.exit(1 if failed else 0)
