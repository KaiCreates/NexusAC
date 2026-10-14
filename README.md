# NexusAC web panel

The in-game NexusAC staff panel, on the web. Same pages, same design, same
buttons: the website serves the panel's own `panel.html` / `panel.css` /
`panel.js`, and the game server answers every request with the same code that
answers staff in game.

## Why it is light

- **No database work while you use it.** Accounts and server keys are one small
  JSON document, read once at start and written only when the owner changes
  them. Live data (players, detections, bans, evidence, settings) is never
  stored here; it comes straight from the game server.
- **Stateless sessions.** A signed cookie, checked with one hash.
- **One open request per game server.** NexusAC keeps a single request open to
  `/api/bridge`; the website hands it work the moment staff click, and the
  answer comes back on the next request. Identical page requests in flight are
  merged, so many staff on the same page cost the game server one answer.
- Three dependencies: starlette, uvicorn, psycopg.

## Layout

```
app/main.py      routes: pages, sign-in, owner tools, the panel transport, the bridge
app/hub.py       the in-memory live link to each game server
app/auth.py      passwords (scrypt), signed cookies, roles
app/store.py     the one JSON document (Postgres row, or data.json locally)
app/panel/       COPIED from NexusAC/html by scripts/sync_panel.py -- do not edit here
app/static/      web.js (the transport), web.css (full-window panel), the site pages' files
app/pages/       sign-in, first-time setup, servers and accounts
```

## Run locally

```bash
pip install -r requirements.txt
COOKIE_SECURE=0 uvicorn app.main:app --port 3000
```

Without `DATABASE_URL` it keeps its state in `data.json`.

## Deploy (Render)

`render.yaml` is a Blueprint. Set `DATABASE_URL` (any Postgres; Neon's pooled
string) in the dashboard. ONE worker only: the live link lives in memory.

## First use

1. Open the site: it asks you to create the **owner** account.
2. **Add server**, name it. The key is shown once, with the two lines for
   `server.cfg` (above `ensure NexusAC`):
   ```
   set nexus_web_url "https://your-site"
   set nexus_web_token "the-key"
   ```
3. Restart NexusAC. The server shows **Connected**; **Open panel**.
4. Add staff accounts with a role: `owner`, `head_admin`, `admin`,
   `moderator`. These are the anti-cheat's own roles -- the game server decides
   what each role may do from its own role table, so a permission change in the
   panel applies on the website too.

Only in game: spectate, live screens and opening ox_inventory (they need a
player to show them to).

## Updating the panel

After changing NexusAC's in-game panel:

```bash
python scripts/sync_panel.py "<path to>/NexusAC"
```

then deploy. The DevTools watch at the end of `panel.js` is the one thing the
script removes.

## Game server side

`NexusAC/server/sv_webpanel.lua` (replaces the old `sv_web.lua`). Console:
`nexusweb` shows the link state.
