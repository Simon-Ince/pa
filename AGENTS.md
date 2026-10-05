# AGENTS.md

Project context for AI coding agents (Cursor, etc.) picking up this repo.

## What this is

"PA Command Center" — a self-hosted, always-on personal dashboard for
Simon Ince (CTO at Lush). Single FastAPI service serves both a JSON API
and a plain HTML/CSS/vanilla-JS frontend (no build step, no npm). Runs via
Docker Compose on Simon's Mac, always up, auto-refreshing via
Server-Sent Events.

Full functional/design history and the current data contracts are in
**README.md** — read that first, it's kept current and is the source of
truth for panel behavior, the triage snapshot JSON shape, the TickTick
API quirk (explicit `/project/inbox/data` call needed), and the calendar
working-location filter logic. Don't duplicate that detail here; this file
is about how to work in the repo, not what it does.

## Stack

- Backend: Python, FastAPI + Uvicorn, single container (`backend/`)
- Frontend: plain HTML/CSS/vanilla JS, served as static files from the
  same FastAPI app (`backend/static/`) — deliberately no React/Vite/build
  step, keep it that way unless Simon explicitly asks to change it
- Orchestration: Docker Compose, one service (`dashboard`), host port
  8420 → container 8000
- Live updates: Server-Sent Events (`/api/stream`), not polling from the
  client — backend polls upstream APIs server-side and pushes deltas

## Key files

```
backend/app/main.py            FastAPI app, routes, static file serving
backend/app/state.py           Central polling loops + aggregated state dict
backend/app/sse.py             SSE stream implementation
backend/app/google_client.py   Gmail unread count + Calendar fetch/filter
backend/app/ticktick_client.py TickTick Open API client
backend/app/focus.py           The FOCUS panel ranking heuristic (no LLM —
                                deliberately plain, inspectable Python logic)
backend/static/index.html      Page structure
backend/static/style.css       Current visual design (Swiss International)
backend/static/app.js          SSE client, rendering, live countdowns
docker-compose.yml             Service definition + read-only bind mounts
.env.example                   Documents required host paths (copy to .env)
README.md                      Full behavior/contract documentation
```

Historical spec files (`SPEC.md`, `SPEC_v2.md`, `SPEC_v3.md`, `SPEC_v4.md`)
are kept in the repo root as a design-decision paper trail — each documents
one iteration's brief. They're reference material, not living docs; if you
change behavior, update **README.md**, not the old SPEC files.

## Current state (as of v5)

Visual style: **Swiss International (International Typographic Style)** —
Inter, black/white/muted plus a single Swiss red `#FF3000` used only as a
signal, 4px black rules, no drop shadows, numbered section labels, a
visible 24px grid. Prior restyles (vaporwave → low-poly Y2K → pastel →
Bauhaus → Swiss) are expected to continue; keep panel/data logic decoupled
from styling so a restyle never has to touch backend code.

Panels are split across six hash-routed tabs (v6), one page visible at a
time, keys 1–6 switch tabs: **Today** (#today) is DECIDE, SLACK/LINEAR,
then TODAY/TOMORROW, TASKS, SIGNAL. **Brief** (#brief) is Daily Brief and
Today's Note. **Technology** (#technology) is the full Slack and Linear
digests. **Meetings** (#meetings) is Recent Meetings with Obsidian
links to the notes each was logged in. **Projects** (#projects) is Active
Projects and Online Presence. **System** (#system) is Triage Pipeline and
Feed Health (per-feed freshness, flags stale/missing feeds). Tab badges
summarise each page (decide count, new brief, tech items that need Simon,
unlogged transcripts, pending drafts, unhealthy feeds). To add a page: a `<nav>` tab + a
`.page[data-page]` block in index.html and the name in `PAGES` in app.js;
new feeds also get a row in `FEEDS` so Feed Health covers them. SIGNAL is
unread-since-last-triage + triage-flagged items, NOT a raw inbox list. A
prior "OPEN LOOPS" panel (Obsidian weekly-note checkboxes) was removed in
v3 — don't re-add it.

## Credentials & mounts — do not break these

Everything reads existing host files read-only via Docker bind mounts;
nothing is copied into the image or ever committed:

- `GOOGLE_TOKEN_PATH` / `GOOGLE_CLIENT_SECRET_PATH` — Simon's existing
  Google OAuth token (has a `refresh_token`; the backend refreshes it via
  `google-auth`, never runs a fresh OAuth flow — don't add one)
- `DASHBOARD_DATA_PATH` — folder containing `triage_snapshot.json`,
  written externally by a separate cron job (not this repo) — read-only
  consumer only
- `TICKTICK_TOKEN_PATH` — TickTick personal API token, `{"token": "..."}`

`.env` is git-ignored and holds the real host paths (see `.env.example`
for the documented defaults, which are Simon's actual paths under
`/Users/simonince/.hermes/profiles/pa/`). Never hardcode credential values
in code or commit anything under `.hermes/`.

## Working conventions

- Real data always. Simon has repeatedly required build verification via
  actual `curl`/screenshot against live data (his real Gmail/Calendar/
  TickTick/triage output) — never stub, mock, or claim something works
  without checking real output. This project's history shows every
  iteration was verified this way; keep doing it.
- Don't crash on upstream failure. Gmail/Calendar/TickTick/triage-snapshot
  each degrade to a clean "unavailable" panel state independently on
  error — the rest of the dashboard must keep working. Preserve this
  pattern in any new data source.
- No new frontend build tooling unless Simon asks — the plain HTML/CSS/JS
  approach is intentional (keeps `docker compose up -d --build` simple
  and fast, no node stage in the Dockerfile).
- After any visual or data change: rebuild (`docker compose up -d
  --build`), curl `/api/state` to confirm real data, and ideally screenshot
  to confirm the visual result — Simon reacts to what he actually sees,
  not descriptions, so get it running and let him look at localhost:8420
  himself when possible.

## Run it

```bash
cp .env.example .env   # only if not already present; holds real host paths
docker compose up -d --build
```
Open http://localhost:8420. Logs: `docker compose logs -f`. Stop:
`docker compose down`.
