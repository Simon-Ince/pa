# PA Command Center — Build Spec

Build a self-hosted personal dashboard for Simon (CTO at Lush). It runs
permanently via Docker Compose on his Mac and shows everything needing his
attention in one place. Visual style: "low-poly Y2K cyber-noir / liminal
gamecore" command center — NOT vaporwave/synthwave (no pink-purple sunset
gradients, no retro grid horizon cliché). Think: dark, moody, slightly
unsettling liminal-space atmosphere; muted desaturated palette with cold
blues/greys/teal and occasional sickly green or amber accent (not hot
magenta/cyan); early-2000s low-poly 3D aesthetic — faceted/angular shapes,
sparse geometric wireframe elements, chunky pixel/bitmap UI accents, subtle
CRT/VHS scanline or noise texture, slightly off perspective grid or empty
low-poly room/corridor vibe in the background (like an abandoned Windows XP
screensaver or a PS1/PS2-era menu screen). Fonts: chunky pixel or early-web
sans (e.g. "Press Start 2P" sparingly for headers, or a clean system
monospace) rather than smooth neon script. Should feel cool, atmospheric,
slightly eerie/liminal — not a corporate dashboard, not a party. Use CSS
animations / canvas — keep it lightweight, no heavy frameworks required.
Prefer plain HTML/CSS/vanilla JS over a frontend build pipeline, to keep
docker-compose simple (no node build step at runtime). Reference mood:
liminal-space photography (empty malls, backrooms), PS1-era low-poly game
menus, Y2K OS UI chrome, cyber-noir (Blade Runner-adjacent but understated,
not garish).

## Stack & repo layout

Repo root: `/Users/simonince/git/Simon-Ince/pa` (already a git repo target,
currently empty — `git init` it).

```
pa/
  docker-compose.yml
  .env.example
  .gitignore
  README.md
  backend/
    Dockerfile
    requirements.txt
    app/
      main.py            # FastAPI app
      google_client.py   # Gmail/Calendar API via refreshed OAuth creds
      weekly_notes.py    # parses current Obsidian weekly note
      state.py           # aggregates + caches the dashboard state
      sse.py             # server-sent events stream
    static/               # served frontend (or top-level frontend/, your call)
      index.html
      style.css
      app.js
```

Single Python service (FastAPI + Uvicorn) that both serves the API and the
static frontend — no separate nginx/node container needed for v1. Use
`docker-compose.yml` (compose v2 syntax, no `version:` key needed) with one
service `dashboard`, exposed on host port `8420` -> container port `8000`.
Add a healthcheck. `docker compose up -d --build` should be all that's
needed to run it, and it should restart on boot (`restart: unless-stopped`).

## Data sources (v1 scope — exactly these four)

### 1. Gmail action items / triage queue (near-real-time)
Read-only Google API access using Simon's already-authorized OAuth token.
Do NOT re-run any OAuth flow — just load and auto-refresh the existing
token file with `google.oauth2.credentials.Credentials` +
`google.auth.transport.requests.Request`, then call the Gmail API directly
via `google-api-python-client`.

Credential files (mount read-only into the container, do not copy into the
image, do not commit to git):
- `/Users/simonince/.hermes/profiles/pa/google_token.json` -> e.g.
  `/secrets/google_token.json:ro`
- `/Users/simonince/.hermes/profiles/pa/google_client_secret.json` -> e.g.
  `/secrets/google_client_secret.json:ro`

Query: unread mail in the primary inbox from the last 3 days
(`is:unread newer_than:3d -category:promotions -category:social`). Show
sender, subject, snippet, received time, Gmail link (`https://mail.google.com/mail/u/0/#inbox/<id>`).
This is the live "unread/needs triage" queue — refresh via polling every
~45-60s server-side, push to clients over SSE so the browser updates without
reload.

### 2. Calendar today/tomorrow (near-real-time)
Same credentials, Calendar API. Fetch events from now through end of
tomorrow. Show time, title, location/meet link if present, and a live
"starts in Xm" countdown computed client-side from the ISO start time (so it
ticks without a refetch). Highlight the next upcoming event distinctly.
Poll server-side every ~60s.

### 3. Weekly Notes open items (Obsidian vault, read-only)
Mount the vault's Weekly Notes folder read-only:
`/Users/simonince/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault/Weekly Notes`
-> `/vault/Weekly Notes:ro` (quote the path in compose, it has spaces).

Find the current week's note (filename pattern `Weekly Notes DD-MM-YY.md`,
Monday of the current week — same convention the PA already uses). Parse
it for unchecked markdown checkboxes (`- [ ]`) grouped by the day heading
they fall under (Monday..Friday). Show each open item with its day. This
only needs to refresh every few minutes (file read is cheap; poll every
~2 min is fine, or watch the file's mtime).

### 4. Message-triage cron output (periodic, not real-time)
There's an existing cron job ("Simon message triage") that runs at 8am and
1pm on weekdays and posts a Slack digest — it does NOT currently write a
machine-readable file. For v1: add a small JSON snapshot step to that
workflow is OUT OF SCOPE for you to build (a human will wire it up
separately). Instead, just build the dashboard to READ a snapshot file if
present at `/Users/simonince/.hermes/profiles/pa/dashboard_data/triage_snapshot.json`
(mount that whole `dashboard_data` directory read-only into the container
at `/data:ro`) and render a "Last triage run" panel from it (timestamp +
summary + item count) if the file exists; otherwise render a clean "no
snapshot yet" empty state — do not error or crash if the file/dir is
missing. Define the exact JSON shape you expect in the README so it's easy
to wire up later, e.g.:
```json
{"generated_at": "2026-08-28T08:00:00Z", "channel": "slack:C0BSZEG2P45",
 "items": [{"summary": "...", "source": "gmail|chat|whatsapp", "link": "..."}]}
```

## Frontend layout

One page, four/five panels in a dashboard grid:
- Header/banner: "PA COMMAND CENTER" wordmark, live clock (Simon's local
  timezone), connection status indicator (small pulsing dot: green = SSE
  connected, amber = reconnecting).
- Panel: INBOX QUEUE (unread Gmail) — scrollable list, newest first, each
  row clickable through to Gmail.
- Panel: TODAY / TOMORROW (calendar) — timeline-style list, next event
  glowing/highlighted, live countdown.
- Panel: OPEN LOOPS (weekly notes) — grouped by day (Mon-Fri), checkbox
  icon styling matching the vaporwave theme.
- Panel: LAST TRIAGE RUN (cron snapshot) — timestamp + item list or empty
  state.
- Small footer status bar: last-updated times per data source, and a
  reconnect indicator if SSE drops.

Use SSE (`EventSource`) for push updates from `/api/stream`; the backend
should push whenever its polling loop detects new data (and periodically as
a heartbeat). Keep payloads small (deltas or the full small state object is
fine given personal-scale data volumes).

## Non-functional requirements

- `.gitignore` must exclude any `.env` with real values, `__pycache__`,
  `node_modules` if any.
- `.env.example` documents the host port and the three mount paths, with
  a real `.env` (git-ignored) the user copies it to.
- README.md: how to run (`docker compose up -d --build`), what each panel
  shows, the triage snapshot JSON contract from section 4, and how to stop
  it, and where to look for logs (`docker compose logs -f`).
- No secrets baked into the image or committed to git — only read-only bind
  mounts of existing host files.
- Handle Google API errors/expired refresh tokens gracefully (log + show a
  "Gmail/Calendar unavailable" state in that panel, don't crash the whole
  app).
- Reasonably fast to build (`pip install` in requirements.txt should be a
  short, standard list: fastapi, uvicorn, google-auth, google-auth-oauthlib,
  google-api-python-client, python-multipart if needed).

## Definition of done

1. `docker compose up -d --build` succeeds from a clean checkout.
2. `curl http://localhost:8420/` returns the dashboard HTML.
3. `curl http://localhost:8420/api/state` returns real JSON with actual
   Gmail unread items and actual calendar events for Simon's account (using
   the mounted token — verify this actually returns live data, not stubs).
4. The Weekly Notes panel shows real open checkbox items from the current
   week's note in the vault.
5. The page visibly matches the vaporwave "command center" brief (animated
   grid/particles, neon glow, monospace type) — take a screenshot if you
   have a way to (e.g. via a headless browser / curl+save + description is
   fine if no screenshot tool) and describe what it looks like in your
   final summary.
6. Git repo initialized with a sensible first commit (do NOT commit .env
   or any credential file).

Report back clearly: what you built, any deviations from spec and why, the
exact commands to start/stop it, and the URL to view it.
