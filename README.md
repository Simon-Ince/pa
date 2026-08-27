# PA Command Center

A self-hosted, always-on personal dashboard for Simon. One FastAPI service
serves both the API and a plain HTML/CSS/JS "vaporwave command center"
frontend, pulling from Gmail, Google Calendar, an Obsidian weekly-notes
vault, and a message-triage cron snapshot.

## Run it

```bash
cp .env.example .env   # adjust paths only if yours differ from the defaults
docker compose up -d --build
```

Then open **http://localhost:8420**.

Stop it:

```bash
docker compose down
```

Logs:

```bash
docker compose logs -f
```

## What each panel shows

- **INBOX QUEUE** — unread Gmail in the primary inbox from the last 3 days
  (`is:unread newer_than:3d -category:promotions -category:social`).
  Sender, subject, snippet, received time; click through to the message in
  Gmail. Polled server-side every ~50s, pushed to the browser over SSE.
- **TODAY / TOMORROW** — Calendar events from now through the end of
  tomorrow. Shows time, title, location/meet link, and a live "starts in
  Xm" countdown that ticks client-side. The next upcoming event is
  highlighted. Polled every ~60s.
- **OPEN LOOPS** — unchecked `- [ ]` items from the current week's Obsidian
  Weekly Note (`Weekly Notes DD-MM-YY.md`, Monday of the current week),
  grouped under the Monday–Friday heading they fall under. Re-parsed every
  ~2 minutes.
- **LAST TRIAGE RUN** — reads a JSON snapshot written by the existing
  "Simon message triage" cron (8am/1pm weekdays → Slack digest). Shows
  timestamp, item count and the list if the snapshot file exists; a clean
  "no snapshot yet" empty state if not. See contract below — wiring up the
  cron to actually write this file is out of scope here.

Footer shows a per-source "last updated" time and an amber "RECONNECTING…"
flag if the SSE connection drops (`EventSource` auto-reconnects).

## Triage snapshot contract

The dashboard reads (read-only) `dashboard_data/triage_snapshot.json`,
mounted into the container at `/data/triage_snapshot.json`. Expected shape:

```json
{
  "generated_at": "2026-08-28T08:00:00Z",
  "channel": "slack:C0BSZEG2P45",
  "items": [
    { "summary": "...", "source": "gmail|chat|whatsapp", "link": "..." }
  ]
}
```

- `generated_at` — ISO 8601 UTC timestamp of the triage run.
- `channel` — where the digest was posted (informational).
- `items` — array of `{ summary, source, link }`. `source` is rendered as a
  small tag; `link` (optional) makes the summary clickable.

If the file is missing, empty, or fails to parse, the panel shows a clean
empty/error state — the app never crashes because of it.

## Data sources & credentials

Read-only bind mounts only — nothing is copied into the image or committed:

- `google_token.json`, `google_client_secret.json` — Simon's existing
  Google OAuth token (already has a `refresh_token`; the backend loads and
  auto-refreshes it via `google-auth`, it never runs an OAuth flow).
- Obsidian vault `Weekly Notes` folder.
- `dashboard_data` folder (triage snapshot).

If Gmail/Calendar auth fails or the token can't be refreshed, those two
panels show a "Gmail/Calendar unavailable" state with the error — the rest
of the dashboard keeps working.

## Stack

FastAPI + Uvicorn (single container), server-sent events for push updates,
plain HTML/CSS/vanilla JS frontend (no build step), Docker Compose.
