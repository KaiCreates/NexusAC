# NexusAC — website

The web console for the NexusAC FiveM anti-cheat. Python (FastAPI), Supabase for
accounts and data, deployable to Vercel.

The design is the Next.js build's, ported over: `app/static/style.css` is that
project's `app/globals.css` with the Tailwind import dropped (every class in it is
semantic — no utility layer was ever used) and asset paths repointed.

```
nexusac-web/
  api/index.py          Vercel entrypoint (exports the ASGI app)
  app/main.py           routes for the pages, error handling
  app/api_routes.py     the JSON API the pages call
  app/bridge.py         the two endpoints the anti-cheat posts to
  app/protocol.py       validation of everything crossing the wire
  app/supabase_auth.py  Supabase Auth (sign-up, sign-in, JWKS verification)
  app/db.py             Postgres access via the Supabase pooler
  app/security.py       sessions, API keys, rate limiting, roles
  migrations/001_init.sql
  scripts/migrate.py    create the tables (safe to re-run)
  scripts/dev.py        run locally on :3000
```

## Run it locally

```bash
pip install -r requirements.txt
python scripts/migrate.py      # once, creates the nx_* tables in Supabase
python scripts/dev.py          # http://localhost:3000
```

`.env` already holds the working values for this Supabase project. It is
gitignored — `SUPABASE_SECRET_KEY` and `DATABASE_URL` are each full access to the
database, so neither belongs in a commit or a screenshot.

`GET /health` reports whether the database is reachable.

## Connecting the anti-cheat

Sign up, press **Add server**, name it. You get a 43-character API key, shown
once — only its SHA-256 hash is stored, so a leak of this database hands out no
working keys. Then in `server.cfg`, above `ensure NexusAC`:

```
set nexus_web_url "https://your-site.vercel.app"
set nexus_web_token "the-43-character-key"
```

The resource accepts either the website origin or a pasted `/api/control/bridge`
URL and normalizes it before connecting. It authenticates every heartbeat with
the bearer key, reports the HTTP error in `nexusweb` when a connection fails, and
backs off automatically during an outage.

`server/sv_web.lua` needs no changes; it already speaks this protocol. It accepts
an `https://` origin, or `http://` only on localhost.

Each server card has a **Connection** panel with the website URL, the config
lines and the key's first characters. The key itself is never shown again — if
it is lost, **Rotate key** in that panel issues a new one and reveals it once.

## Two dashboards

**`/demo`** — the interactive live demo, ported from the Next.js build's
`components/dashboard.tsx` and `lib/demo.ts`. All thirteen sections (overview with
the activity chart, servers, players, detections, bans, screenshots, Protection
Center, Event Protection, logs, staff, integrations, license, settings), the
simulated 5-second activity feed, the investigation and configuration drawers.
Needs no account and never calls the API — the state lives in the page and resets
on reload. It is what someone sees before they sign up.

**`/dashboard`** — the real thing, backed by the live bridge. Sign in, add a
server, and its console gives you:

| Tab | What it does |
|---|---|
| Overview | mode, uptime, players, entity counters, registry, webhook health |
| Players | live roster with risk, ping, lifecycle, ped, HP/armour — kick, ban, freeze, screenshot |
| Detections | the live signal feed with weight and running risk |
| Detectors | every detector's maturity and mode; switch between disabled / observe / enforce |
| Bans | the ban list with linked evidence; unban from here |
| Evidence | cases with detector, confidence, signals and screenshots |
| Logs | everything the resource recorded |
| Configuration | the whitelisted settings schema, edited in place |

Configuration edits and detector changes are queued as commands carrying the value
the page is showing, so a stale page cannot overwrite a newer value on the server.

## Deploying to Render

1. Push this repository, then at render.com choose **New → Blueprint** and pick it.
   `render.yaml` sets the build and start commands and the `/health` check.
   (Manually instead: New → Web Service, build `pip install -r requirements.txt`,
   start `python scripts/migrate.py && uvicorn app.main:app --host 0.0.0.0 --port $PORT`.)
2. Render prompts for the environment variables marked `sync: false`. Copy them
   from your local `.env`, and set `APP_URL` to the Render URL it gives you
   (`https://<service>.onrender.com`) — the CSRF origin check and the `Secure`
   cookie flag both read it.
3. Point the resource at it and restart:

```
set nexus_web_url "https://<service>.onrender.com"
set nexus_web_token "the-43-character-key"
```

The app reads `$PORT`, so it needs no Render-specific code. On the free plan a
service sleeps after inactivity — but the anti-cheat polls every few seconds, so
a connected server keeps it awake by itself. A cold start still costs the first
sync a timeout; it retries with backoff.

## Deploying to Vercel

1. Push this folder to a repository and import it in Vercel. `vercel.json`
   rewrites every path to the Python function; no build step is needed.
2. Add these environment variables in Vercel → Settings → Environment Variables
   (copy the values from `.env`, and set `APP_URL` to the deployed URL):
   `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`,
   `SUPABASE_JWKS_URL`, `DATABASE_URL`, `APP_URL`, `REQUIRE_EMAIL_CONFIRMATION`.
3. Deploy, then point `nexus_web_url` at the Vercel URL and restart the resource.

`DATABASE_URL` uses the Supavisor **transaction pooler** on port 6543, not the
direct host. Supabase's direct database host resolves to IPv6 only, which Vercel
functions cannot reach. Prepared statements are disabled in `app/db.py` for the
same reason — a transaction-mode pooler cannot carry one across statements.

## Accounts and email confirmation

Supabase Auth owns identity: it stores and hashes passwords and handles password
resets. The website reads the user id out of the freshly issued JWT (verified
against the project JWKS, ES256) and then mints its own opaque session cookie, so
rendering a page never depends on refreshing a Supabase token.

This project has email confirmation **on** with Supabase's built-in mailer, which
is rate limited to a handful of messages an hour — enough to make sign-up look
broken. So `REQUIRE_EMAIL_CONFIRMATION=false` creates accounts pre-confirmed
through the admin API and signs the person straight in. Configure your own SMTP
provider in Supabase, then set it to `true` to get real verification.

## Roles

| Role | Can do |
|---|---|
| owner | everything, plus staff, API keys and removing servers |
| administrator | kick, ban, unban, freeze, screenshot, settings, detectors |
| moderator | kick, freeze, screenshot |
| viewer | read only |

Staff join by redeeming a 24-hour single-use invite code. Every action is written
to the audit log.

## How the bridge works

The resource polls `POST /api/control/bridge/sync` every ~3 seconds with a full
snapshot and gets back at most one queued command. Screenshots go to
`POST /api/control/bridge/media`. Both authenticate with the API key as a bearer
token — never a cookie — so no browser can drive them.

Guarantees that matter, all covered by tests:

- **Replay is refused.** Each resource start gets a new boot id, and sequence
  numbers must increase within it. A retired boot id cannot be reused.
- **Clocks must agree** within 90 seconds, or the snapshot is refused.
- **Commands run exactly once.** Each carries a receipt id the resource persists
  before executing; a retry after a dropped connection returns the previous
  result instead of running the action again.
- **Commands expire** after 60 seconds and carry the value they expect to act on.
  If the player's session, the ban, the setting or the detector mode changed in
  between, the anti-cheat refuses rather than acting on stale intent.
- **Only one command is in flight** at a time, so an expected-value check always
  sees the result of the command before it.
- **Workspaces are isolated** — another account gets a 404, not a 403, for a
  server it does not own.

## Tests

In `tests/`. They need `lupa` (for the Lua suite) and `playwright` (for the browser suite):

- `e2e.py` — 61 checks over accounts, keys, the bridge protocol, commands,
  evidence, workspace isolation, CSRF and key rotation.
- `realbridge.py` — 14 checks that load the **real** `server/sv_web.lua` under
  lupa with a stubbed FiveM runtime and let it drive this site over real HTTP:
  sync, command dispatch, execution, receipt persistence, acknowledgement.
- `uicheck.py` — 21 checks in Chromium asserting every page renders real data,
  every icon name resolves, and no page throws a JavaScript error.
- `democheck.py` — 45 checks driving the live demo: all thirteen sections, deep
  links, drawers, search, filters, server switching, ban revocation, event and
  staff editing, reset, and that it never calls the real API.

Run them with the site up:

```bash
python tests/e2e.py        http://localhost:3000
python tests/realbridge.py http://localhost:3000
python tests/uicheck.py    http://localhost:3000
python tests/democheck.py  http://localhost:3000
```

`realbridge.py` takes the resource folder as a second argument; it defaults to
`../NexusAC` next to this one.

## Security notes

- API keys are stored only as SHA-256; the plaintext is shown once at creation.
- All `nx_*` tables have RLS enabled with no policies, and `anon`/`authenticated`
  are revoked. Anyone holding only the publishable key gets nothing from
  PostgREST.
- Mutating requests are origin-checked. The session cookie is `HttpOnly`,
  `SameSite=Lax`, and `Secure` in production.
- Rate limits: sign-in per email and globally, bridge sync per server, commands
  per user, invites per workspace.
- The snapshot never carries webhook URLs or role grants — the resource masks
  them before they leave the server.
