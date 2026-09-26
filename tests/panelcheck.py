"""The configuration page, the Screenshots section, and adding staff by username."""
import base64, json, sys, time
import httpx
from playwright.sync_api import sync_playwright

SITE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000"
OUT = sys.argv[2] if len(sys.argv) > 2 else "."
PW = "correct-horse-battery-staple-9"
stamp = int(time.time())
OWNER = "panel+%d@nexusac.test" % stamp
MATE = "mate+%d@nexusac.test" % stamp

passed, failed = [], []
def check(name, ok, detail=""):
    (passed if ok else failed).append(name)
    print(("  PASS  " if ok else "  FAIL  ") + name + (("  -> " + str(detail)[:220]) if detail and not ok else ""))

owner = httpx.Client(base_url=SITE, timeout=40, headers={"Origin": SITE})
owner.post("/api/control/auth/register", json={"email": OWNER, "password": PW, "name": "KaiOwner%d" % stamp})
r = owner.post("/api/control/servers", json={"name": "Config Test"})
TOKEN, SERVER_ID = r.json()["token"], r.json()["id"]

# A second real account, so "add by username" has someone to find.
mate = httpx.Client(base_url=SITE, timeout=40, headers={"Origin": SITE})
mate.post("/api/control/auth/register", json={"email": MATE, "password": PW, "name": "Mate%d" % stamp})

EV = "boot-cfg:NX-E-7001"
SETTINGS = {
    "general.mode": {"value": "enforce", "kind": "enum", "live": True,
                     "values": {"observe": True, "enforce": True}},
    "general.debug": {"value": False, "kind": "boolean", "live": True},
    "risk.ban": {"value": 160, "kind": "number", "live": True, "lo": 1, "hi": 1000},
    "risk.kick": {"value": 110, "kind": "number", "live": True, "lo": 1, "hi": 1000},
    "risk.flag": {"value": 40, "kind": "number", "live": True, "lo": 1, "hi": 1000},
    "risk.decayPerMinute": {"value": 3, "kind": "number", "live": True, "lo": 0, "hi": 200},
    "cursor.enabled": {"value": True, "kind": "boolean", "live": False},
    "godmode.enabled": {"value": True, "kind": "boolean", "live": True},
    "rpfblock.signature.five_x_zoom": {
        "value": True, "kind": "boolean", "live": True,
        "label": "5X weapon zoom", "note": "weapons.meta",
    },
    "combat.enabled": {"value": True, "kind": "boolean", "live": True},
    "ipbans.enabled": {"value": True, "kind": "boolean", "live": True},
    "ipbans.expireDays": {"value": 30, "kind": "number", "live": True, "lo": 0, "hi": 3650},
    "identityguard.thresholdDeny": {"value": 90, "kind": "number", "live": True, "lo": 1, "hi": 100},
    "banmessage.appealText": {"value": "Contact staff.", "kind": "string", "live": True},
}
snapshot = {
    "overview": {"mode": "enforce", "version": "1.4.0", "uptime": 900, "online": 2,
                 "watched": 0, "scored": 0, "clientless": 0,
                 "thresholds": {"flag": 40, "kick": 110, "ban": 160}},
    "players": [
        {"src": 3, "name": "Marcus", "risk": 0, "ping": 40, "frozen": False, "sessionKey": "k3",
         "lifecycle": "NORMAL", "live": True},
        {"src": 7, "name": "Luna", "risk": 0, "ping": 55, "frozen": False, "sessionKey": "k7",
         "lifecycle": "NORMAL", "live": True},
    ],
    "detectors": [], "bans": [], "feed": [], "logs": [],
    "config": {"settings": SETTINGS, "profile": "default"},
    "events": {}, "integrations": {"screenshots": "started", "webhooks": []},
    "evidence": [{"id": EV, "resourceId": "NX-E-7001", "at": int(time.time()) - 40,
                  "detection": "Godmode", "detector": "NX-GODMODE-001", "confidence": 88,
                  "action": "ban", "player": {"name": "Marcus", "src": 3},
                  "detail": {}, "signals": [], "screenshot": {"status": "captured"}},
                 {"id": "boot-cfg:NX-E-7002", "resourceId": "NX-E-7002",
                  "at": int(time.time()) - 20, "detection": "Manual screenshot",
                  "detector": "staff", "confidence": 0, "action": "review",
                  "player": {"name": "Luna", "src": 7}, "detail": {}, "signals": [],
                  "screenshot": {"status": "unavailable", "why": "Nexus-Screens is not running"}}],
}
httpx.post(SITE + "/api/control/bridge/sync",
           headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
           content=json.dumps({"protocol": 1, "boot": "boot-cfg", "sequence": 1,
                               "sentAt": int(time.time()), "snapshot": snapshot,
                               "acknowledgements": []}), timeout=40)
jpeg = base64.b64encode(bytes.fromhex("ffd8ff") + b"\x00" * 900).decode()
for slot in (0, 1):
    httpx.post(SITE + "/api/control/bridge/media", headers={"Authorization": "Bearer " + TOKEN},
               json={"evidenceId": EV, "slot": slot, "data": "data:image/jpeg;base64," + jpeg},
               timeout=40)

errors = []
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 1050})
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(SITE + "/login", wait_until="networkidle")
    page.fill("#email", OWNER); page.fill("#password", PW)
    page.click("button[type=submit]")
    page.wait_for_url("**/dashboard", timeout=20000)

    print("\n== configuration ==")
    page.goto(SITE + "/dashboard/servers/" + SERVER_ID, wait_until="networkidle")
    page.wait_for_timeout(1600)
    page.click(".sidebar-link[data-tab='Configuration']")
    page.wait_for_timeout(700)

    cards = page.locator(".cfg-card").count()
    check("settings are grouped into module cards", cards >= 6, "%d cards" % cards)
    check("no flat settings table remains", page.locator("#view table").count() == 0)
    check("card headers are titled", "Risk" in page.inner_text(".cfg-grid"))
    check("search box present", page.locator("#cfg-search").count() == 1)
    check("tabs present", page.locator("[data-cfgtab]").count() >= 4)
    check("RPF switch uses its operator label",
          page.locator("[data-cfg='rpfblock.signature.five_x_zoom']").count() == 1
          and "5X weapon zoom" in page.inner_text(".cfg-grid"))
    check("RPF switch shows the affected file", "weapons.meta" in page.inner_text(".cfg-grid"))
    check("Save starts disabled", page.locator("#cfg-save").is_disabled())
    page.screenshot(path=OUT + "/cfg-grouped.png", full_page=False)

    # Tab filtering
    page.click("[data-cfgtab='Core']")
    page.wait_for_timeout(400)
    core = page.inner_text(".cfg-grid")
    check("Core tab narrows the cards", "Risk" in core and "Ipbans" not in core, core[:120])
    page.click("[data-cfgtab='All']")
    page.wait_for_timeout(400)

    # Search
    page.click("#cfg-search")
    page.type("#cfg-search", "risk.", delay=30)
    page.wait_for_timeout(600)
    check("search narrows to matching settings",
          page.locator(".cfg-card").count() == 1, page.locator(".cfg-card").count())
    check("search keeps focus",
          page.evaluate("document.activeElement && document.activeElement.id") == "cfg-search")
    page.fill("#cfg-search", "")
    page.wait_for_timeout(500)

    # Stage a toggle and a number, confirm nothing is sent until Save
    before = len(owner.get("/api/control/workspace").json()["commands"])
    page.locator("[data-cfg='godmode.enabled']").click()
    page.wait_for_timeout(400)
    check("toggling stages instead of sending",
          page.locator(".cfg-row.staged").count() == 1,
          page.locator(".cfg-row.staged").count())
    check("Save becomes enabled", not page.locator("#cfg-save").is_disabled())
    check("Save shows the staged count", "(1)" in page.inner_text("#cfg-save"),
          page.inner_text("#cfg-save"))

    page.fill("[data-cfg='risk.ban']", "200")
    page.locator("[data-cfg='risk.ban']").press("Tab")
    page.wait_for_timeout(500)
    check("editing a number also stages", "(2)" in page.inner_text("#cfg-save"),
          page.inner_text("#cfg-save"))
    mid = len(owner.get("/api/control/workspace").json()["commands"])
    check("still nothing sent before Save", mid == before, "%d -> %d" % (before, mid))
    page.screenshot(path=OUT + "/cfg-staged.png", full_page=False)

    page.click("#cfg-save")
    page.wait_for_timeout(3000)
    after = owner.get("/api/control/workspace").json()["commands"]
    settings_cmds = [c for c in after if c["body"]["type"] == "setting"]
    check("Save queues one command per change", len(settings_cmds) == 2,
          [c["body"] for c in settings_cmds])
    paths = sorted(c["body"]["path"] for c in settings_cmds)
    check("both edited paths were sent", paths == ["godmode.enabled", "risk.ban"], paths)
    check("the number was sent as a number",
          any(c["body"]["path"] == "risk.ban" and c["body"]["value"] == 200 for c in settings_cmds),
          [c["body"] for c in settings_cmds])
    check("staged markers clear after saving", page.locator(".cfg-row.staged").count() == 0)

    # Out-of-range is refused locally
    page.fill("[data-cfg='identityguard.thresholdDeny']", "500")
    page.locator("[data-cfg='identityguard.thresholdDeny']").press("Tab")
    page.wait_for_timeout(500)
    check("out-of-range value is refused", "must be at most 100" in page.inner_text("#msg"),
          page.inner_text("#msg"))

    print("\n== screenshots section ==")
    page.click(".sidebar-link[data-tab='Screenshots']")
    page.wait_for_timeout(900)
    check("screenshots is its own section",
          page.locator(".shot-layout").count() == 1)
    check("player rail lists who can be captured",
          page.locator(".shot-rail-row").count() == 2,
          page.locator(".shot-rail-row").count())
    check("rail offers a capture button per player",
          page.locator(".shot-rail-row [data-act='screenshot']").count() == 2)
    tiles = page.locator(".shot-tile").count()
    check("gallery shows every captured image", tiles == 2, "%d tiles" % tiles)
    check("a healthy Nexus-Screens shows no warning",
          page.locator(".notice.bad").count() == 0)
    # A requested capture that produced no image must still be visible and explained.
    check("attempts without an image are listed",
          page.locator(".shot-pending").count() == 1,
          page.locator(".shot-pending").count())
    pend = page.inner_text(".shot-pending-list")
    check("the failed attempt names the player and the reason",
          "Luna" in pend and "unavailable" in pend and "Nexus-Screens" in pend, pend[:180])
    check("nav badge counts the screenshots",
          page.inner_text("#count-shots").strip() == "2", page.inner_text("#count-shots"))
    page.screenshot(path=OUT + "/shots-section.png", full_page=False)

    page.locator(".shot-tile").first.click()
    page.wait_for_timeout(800)
    check("clicking a tile opens the viewer", page.locator("dialog.drawer[open]").count() == 1)
    check("viewer shows the full image", page.locator("dialog.drawer .shot-full img").count() == 1)
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)

    print("\n== staff by username ==")
    page.goto(SITE + "/dashboard", wait_until="networkidle")
    page.wait_for_timeout(1200)
    page.click(".sidebar-link[data-view='staff']")
    page.wait_for_timeout(500)
    page.click("#invite")
    page.wait_for_timeout(500)
    check("dialog asks for a username or email",
          page.locator("dialog.drawer #identifier").count() == 1)

    page.fill("dialog.drawer #identifier", "Mate%d" % stamp)
    page.select_option("dialog.drawer #role", "moderator")
    page.click("dialog.drawer #add")
    page.wait_for_timeout(2000)
    check("adding by username closes the dialog",
          page.locator("dialog.drawer[open]").count() == 0)
    body = page.inner_text("#view")
    check("the person now appears in staff", ("Mate%d" % stamp) in body, body[:200])
    check("with the chosen role", "moderator" in body)

    # Unknown person falls back to an invite code
    page.click("#invite")
    page.wait_for_timeout(500)
    page.fill("dialog.drawer #identifier", "nobody-called-this-%d" % stamp)
    page.click("dialog.drawer #add")
    page.wait_for_timeout(1800)
    fallback = page.inner_text("dialog.drawer")
    check("unknown username falls back to an invite code",
          "has an account yet" in fallback and page.locator("dialog.drawer .key-reveal").count() == 1,
          fallback[:200])
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)

    print("\n== workspace switcher ==")
    page.click("#workspace-picker")
    page.wait_for_timeout(600)
    check("the picker opens a workspace list",
          page.locator("dialog.drawer .ws-row").count() >= 1,
          page.locator("dialog.drawer .ws-row").count())
    check("the current workspace is marked and not clickable",
          page.locator("dialog.drawer .ws-row.current").count() == 1
          and page.locator("dialog.drawer .ws-row.current").is_disabled())
    page.keyboard.press("Escape")

    browser.close()

# Being added does not move you into that workspace -- it becomes available to
# switch to, which is what the picker is for.
r = mate.get("/api/control/workspace")
spaces = r.json()["workspaces"]
check("the workspace appears for the added member", len(spaces) == 2, spaces)
target = next((w for w in spaces if w["id"] != r.json()["user"]["workspace"]), None)
check("they can switch into it",
      mate.post("/api/control/workspace/switch", json={"id": target["id"]}).status_code == 200)
after = mate.get("/api/control/workspace").json()
check("and land in the right role there", after["user"]["role"] == "moderator",
      after["user"]["role"])
check("seeing the owner's server", any(s["name"] == "Config Test" for s in after["servers"]),
      after["servers"])
check("a moderator cannot add a server",
      mate.post("/api/control/servers", json={"name": "nope"}).status_code == 403)

real = [e for e in errors if "favicon" not in e.lower()]
check("no javascript errors", not real, real[:3])

print("\n%d passed, %d failed" % (len(passed), len(failed)))
if failed:
    print("FAILED: " + ", ".join(failed))
sys.exit(1 if failed else 0)
