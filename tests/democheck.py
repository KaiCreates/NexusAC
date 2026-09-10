"""Drive the live demo in a real browser: every section renders, and the
interactive parts actually change state."""
import sys
from playwright.sync_api import sync_playwright

SITE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000"
OUT = sys.argv[2] if len(sys.argv) > 2 else "."

passed, failed = [], []
def check(name, ok, detail=""):
    (passed if ok else failed).append(name)
    print(("  PASS  " if ok else "  FAIL  ") + name + (("  -> " + str(detail)[:200]) if detail and not ok else ""))

errors = []
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1500, "height": 1000})
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))

    print("\n== sections ==")
    page.goto(SITE + "/demo", wait_until="networkidle")
    page.wait_for_timeout(1200)
    check("demo boots on overview", "Everything under control." in page.inner_text("#demo-root"))
    check("stat tiles rendered", page.locator("#demo-root .stats-grid .panel.stat").count() == 4)
    check("chart drawn", page.locator("#demo-root .chart-plot svg path").count() >= 1)
    check("protection health shown", "modules enabled" in page.inner_text(".health-panel"))
    check("live activity listed", page.locator(".activity-list .activity-item").count() >= 3)
    page.screenshot(path=OUT + "/demo-overview.png", full_page=False)

    expected = {
        "servers": "No Limits RP", "players": "Player directory", "detections": "Silent Aim",
        "bans": "Ban history", "screenshots": "SIMULATED EVIDENCE",
        "protection": "Combat protection", "events": "bank:transfer",
        "logs": "Activity & audit trail", "staff": "Workspace members",
        "integrations": "Discord notifications", "license": "NexusAC Pro",
        "settings": "Workspace preferences",
    }
    for section, needle in expected.items():
        page.click(".sidebar-link[data-section='%s']" % section)
        page.wait_for_timeout(350)
        body = page.inner_text("#demo-root")
        check("section %s renders" % section, needle in body, body[:150])
        if section in ("protection", "detections", "logs"):
            page.screenshot(path=OUT + "/demo-%s.png" % section, full_page=False)

    print("\n== url + navigation ==")
    check("url tracks the section", page.url.endswith("/demo/settings"), page.url)
    page.goto(SITE + "/demo/protection", wait_until="networkidle")
    page.wait_for_timeout(900)
    check("deep link opens that section", "Combat protection" in page.inner_text("#demo-root"))
    check("sidebar marks it active",
          page.locator(".sidebar-link[data-section='protection'].active").count() == 1)

    print("\n== interaction ==")
    # Toggle a protection module off and watch the counter move.
    before = page.inner_text(".notice")
    page.locator("[data-protect]").first.click()
    page.wait_for_timeout(500)
    after = page.inner_text(".notice")
    check("toggling a module changes the enabled count", before != after, before + " -> " + after)
    check("a toast confirms the change", page.locator(".toast").count() == 1)

    # Open the module configuration drawer and save a change.
    page.locator("[data-edit]").first.click()
    page.wait_for_timeout(500)
    check("module drawer opens", page.locator("dialog.drawer[open]").count() == 1)
    check("drawer has the enforcement segmented control",
          page.locator("dialog.drawer .segmented button").count() == 3)
    page.locator("dialog.drawer [data-action='Kick']").click()
    page.locator("dialog.drawer button[type=submit]").click()
    page.wait_for_timeout(600)
    check("drawer closes after save", page.locator("dialog.drawer[open]").count() == 0)
    check("enforcement change is reflected", "Kick at" in page.inner_text("#demo-root"))

    # Detection investigation drawer.
    page.click(".sidebar-link[data-section='detections']")
    page.wait_for_timeout(350)
    page.locator("[data-investigate]").first.click()
    page.wait_for_timeout(500)
    drawer = page.inner_text("dialog.drawer")
    check("investigation drawer opens", "SIMULATED EVIDENCE" in drawer, drawer[:150])
    check("it shows sample identifiers", "license:demo-" in drawer)
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)

    # Search filters the table. Click into the field and type it out, the way a
    # person does: closing a <dialog> restores focus asynchronously, so filling
    # the instant after Escape races the browser rather than testing the page.
    page.click("#search")
    page.type("#search", "Marcus", delay=40)
    page.wait_for_timeout(600)
    rows = page.locator("#demo-root tbody tr").count()
    check("search filters detections", rows == 1, "%d rows" % rows)
    check("search keeps focus while typing",
          page.evaluate("document.activeElement && document.activeElement.id") == "search")
    check("the typed text survives the table redraw",
          page.eval_on_selector("#search", "e => e.value") == "Marcus")
    page.fill("#search", "")
    page.wait_for_timeout(400)

    # Category filter.
    page.click("[data-category='Injection']")
    page.wait_for_timeout(400)
    body = page.inner_text("#demo-root")
    check("category filter applies", "Executor Injection" in body and "Silent Aim" not in body)
    page.click("[data-category='All']")
    page.wait_for_timeout(300)

    # Server switching.
    page.select_option("#server-select", "staging")
    page.wait_for_timeout(500)
    check("switching to an offline server updates the toolbar",
          "Offline" in page.inner_text(".server-toolbar"))
    page.select_option("#server-select", "no-limits")
    page.wait_for_timeout(400)

    # Revoke a ban through the confirm dialog.
    page.click(".sidebar-link[data-section='bans']")
    page.wait_for_timeout(400)
    page.locator("[data-revoke]").first.click()
    page.wait_for_timeout(400)
    check("revoke asks for confirmation", "Revoke this sample ban?" in page.inner_text("dialog.drawer"))
    page.locator("dialog.drawer [data-confirm]").click()
    page.wait_for_timeout(600)
    check("ban shows as revoked", "Revoked" in page.inner_text("#demo-root"))

    # Add a protected event.
    page.click(".sidebar-link[data-section='events']")
    page.wait_for_timeout(400)
    page.click("[data-add-event]")
    page.wait_for_timeout(400)
    page.fill("dialog.drawer input[name=name]", "garage:storeVehicle")
    page.fill("dialog.drawer input[name=resource]", "qb-garages")
    page.locator("dialog.drawer button[type=submit]").click()
    page.wait_for_timeout(600)
    check("new event appears in the table", "garage:storeVehicle" in page.inner_text("#demo-root"))

    # Staff member add + remove.
    page.click(".sidebar-link[data-section='staff']")
    page.wait_for_timeout(400)
    page.click("[data-invite]")
    page.wait_for_timeout(400)
    page.fill("dialog.drawer input[name=email]", "newmod@example.test")
    page.locator("dialog.drawer button[type=submit]").click()
    page.wait_for_timeout(600)
    check("staff member added", "newmod@example.test" in page.inner_text("#demo-root"))
    page.locator("[data-remove-staff='newmod@example.test']").click()
    page.wait_for_timeout(500)
    check("staff member removed", "newmod@example.test" not in page.inner_text("#demo-root"))

    # Live stream pause.
    page.click(".sidebar-link[data-section='logs']")
    page.wait_for_timeout(400)
    page.locator("[data-stream]").first.click()
    page.wait_for_timeout(400)
    check("live feed can be paused", "Resume" in page.inner_text("#demo-root"))

    # Reset restores the revoked ban.
    page.click(".sidebar-link[data-section='settings']")
    page.wait_for_timeout(400)
    page.click("[data-reset]")
    page.wait_for_timeout(400)
    page.locator("dialog.drawer [data-confirm]").click()
    page.wait_for_timeout(700)
    page.click(".sidebar-link[data-section='bans']")
    page.wait_for_timeout(400)
    check("reset restores sample data", "Revoked" not in page.inner_text("#demo-root"))

    print("\n== demo is isolated from the real site ==")
    requests = []
    page.on("request", lambda r: requests.append(r.url))
    page.goto(SITE + "/demo", wait_until="networkidle")
    page.wait_for_timeout(6500)  # long enough for a simulated tick
    api_calls = [u for u in requests if "/api/control" in u]
    check("demo never calls the real API", not api_calls, api_calls[:3])
    check("simulated tick advanced the feed",
          page.locator(".activity-list .activity-item").count() >= 3)

    print("\n== entry points ==")
    for path, selector in [("/", "a.button[href='/demo']"),
                           ("/login", "a.auth-demo[href='/demo']")]:
        page.goto(SITE + path, wait_until="networkidle")
        check("demo linked from %s" % path, page.locator(selector).count() >= 1)

    browser.close()

real_errors = [e for e in errors if "favicon" not in e.lower()]
check("no javascript errors anywhere in the demo", not real_errors, real_errors[:3])

print("\n%d passed, %d failed" % (len(passed), len(failed)))
if failed:
    print("FAILED: " + ", ".join(failed))
sys.exit(1 if failed else 0)
