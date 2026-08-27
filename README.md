# PA Command Center

A self-hosted, always-on personal dashboard for Simon. One FastAPI service
serves both the API and a plain HTML/CSS/JS frontend — clean, bold,
pastel-on-white, thick-outlined panel design (v3) — pulling from Gmail,
Google Calendar, a message-triage cron snapshot, and TickTick.

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

- **FOCUS** — full-width hero strip at the top, the "what should I actually
  look at right now" list, given room to breathe rather than a cramped box.
  Computed server-side every ~20s by a plain heuristic in
  `backend/app/focus.py` (no LLM call — deliberately kept inspectable). It
  combines the other three sources into a single ranked list, capped at 5
  items, deduped by text, ranked in this order (highest priority first):
  1. triage items flagged `urgent`
  2. calendar meetings starting within the next 60 minutes
  3. overdue TickTick tasks
  4. TickTick tasks due today
  5. triage items flagged as needing a `reply`
  Each item is tagged with the source it came from (`SIGNAL` / `MEETING` /
  `TASK`) so it's traceable back to the panel it was derived from — the tag
  colour matches that panel's accent colour. If nothing qualifies it shows
  "Nothing urgent — clear to focus" rather than an empty box.
- **TODAY / TOMORROW** — Calendar events from now through the end of
  tomorrow, with all-day "working location" markers filtered out (see
  below). Shows time, title, location/meet link, and a live "starts in
  Xm" countdown that ticks client-side. The next upcoming event is
  highlighted. Polled every ~60s.
- **SIGNAL** — shows a prominent live unread count (`is:unread
  newer_than:3d -category:promotions -category:social` against the primary
  inbox, cheap `resultSizeEstimate` call — no per-message fetch), and below
  it the items the existing "Simon message triage" cron judged worth
  surfacing, read from its JSON snapshot (see contract below). Each item
  shows its source (`gmail`/`chat`/etc) and urgency; `urgent` items get a
  brighter amber treatment. If the snapshot is more than ~7 hours old *and*
  it's currently a weekday between 8am and 6pm, a "STALE" flag appears next
  to it (the data itself is still shown, never hidden).
- **TASKS** — Simon's incomplete TickTick to-dos. See the TickTick section
  below for the data contract and one non-obvious API quirk. Polled every
  ~2.5 minutes (no need for SSE-fast refresh on todos).

Below FOCUS, the three panels sit in a 12-column grid sized to their real
content volume rather than uniform equal boxes: CALENDAR (narrower,
timeline-shaped, ~6 items) spans 4 columns, TASKS (up to 15 items) spans 5,
SIGNAL (up to 8 items) spans 3. Panels scroll internally only if content
genuinely exceeds the available height.

Footer shows a per-source "last updated" time and an amber "RECONNECTING…"
flag if the SSE connection drops (`EventSource` auto-reconnects).

## v3: OPEN LOOPS panel removed

The Weekly Notes / OPEN LOOPS panel (unchecked `- [ ]` items from the
current week's Obsidian Weekly Note) has been removed entirely — Simon
uses TickTick as his real task system now, and the panel was redundant.
This removed the `weekly_notes` backend polling loop, the `weekly_notes`
key from `/api/state`, `backend/app/weekly_notes.py`, and the Obsidian
vault read-only bind mount + `VAULT_WEEKLY_NOTES_PATH`/`VAULT_WEEKLY_NOTES_DIR`
env vars from `docker-compose.yml`/`.env.example` (nothing else needed the
vault mount). FOCUS's "today's open weekly-note items" ranking tier was
dropped along with it — the ranking list above reflects the current
(5-tier) order.

## v3: visual redesign

The old "low-poly Y2K cyber-noir / liminal gamecore" dark/glitch look
(scanlines, noise, grain, ambient canvas dust/facets, pixel font) has been
replaced with a clean, bold, pastel design:

- **Base**: near-white/cream canvas (`#faf7f1`) with near-black ink
  (`#221f1b`) text, thick 3px black borders as the core structural motif
  (panels, header/footer dividers) instead of drop shadows or glow.
  Rounded corners throughout (22px panels, 14px row cards, pill-shaped
  tags/badges) — consistent, no mixing with sharp corners.
- **Type**: Space Grotesk (bold, geometric) for headings/labels/numbers,
  Inter for body text — replacing "Press Start 2P" + "JetBrains Mono".
- **One pastel accent per panel**, wash fill + deeper accent tone for text/
  borders/tags:
  - FOCUS — sky-blue (`#dcedfc` wash / `#1c6fb0` deep)
  - CALENDAR — mint (`#d9f2e3` wash / `#1f8a5f` deep)
  - TASKS — peach (`#ffe4d1` wash / `#c9642c` deep)
  - SIGNAL — lavender (`#e9e0fb` wash / `#6a4fc4` deep)
  - Status accents: butter-amber (`#fff3c4` / `#a97b0a`) for urgent/stale
    flags and the live connection dot; coral (`#ffe1de` / `#c9433a`) for
    overdue tasks/errors.
- **Micro-animations, not atmosphere**: the ambient canvas (drifting dust
  motes, wireframe facets), scanline/noise overlays, and flickering-light
  divs are gone. In their place: a soft pulse on the live connection dot,
  and a short fade/slide-in on newly rendered list rows.

## Calendar filter behavior

Google Calendar events that are all-day working-location markers
("Home"/"Office"/etc, created by Calendar's "Working Locations" feature)
are filtered out of the TODAY/TOMORROW panel — they're not real meetings.
`backend/app/google_client.py`'s `_is_working_location()` prefers checking
the API's own `eventType == "workingLocation"` field (confirmed against
Simon's real calendar — his recurring "Home" all-day entries carry this
field) and falls back to a summary denylist (`home`, `office`, `working
from home`, `wfh`) for any edge case that might lack it. Verified on real
data: the raw feed for 27–28 Aug 2026 returned 8 events including two
all-day "Home" entries; after filtering, 6 real timed events remained.
Non-`workingLocation` all-day events (e.g. birthdays) are *not* filtered —
only the working-location denylist/eventType match is excluded. If this
list needs adjusting, it's the one place to edit — see the comment there.

## Gmail panel behavior (changed in v2)

The old panel listed raw unread messages; that's gone. Gmail now only
feeds a live unread *count* into the SIGNAL panel (see above) — for actual
message triage, the SIGNAL panel's triage-flagged items are the intended
path, not scrolling raw unread mail.

## Triage snapshot contract

The dashboard reads (read-only) `dashboard_data/triage_snapshot.json`,
mounted into the container at `/data/triage_snapshot.json`. Expected shape:

```json
{
  "generated_at": "2026-08-28T08:00:00Z",
  "channel": "slack:C0BSZEG2P45",
  "unread_count": 34,
  "items": [
    {
      "summary": "...",
      "source": "gmail|chat|whatsapp",
      "urgency": "urgent|reply|action|waiting",
      "link": "..."
    }
  ]
}
```

- `generated_at` — ISO 8601 UTC timestamp of the triage run.
- `channel` — where the digest was posted (informational).
- `unread_count` — informational count from the triage run itself (the
  SIGNAL panel's headline count is the *live* Gmail count, not this field).
- `items` — array of `{ summary, source, urgency, link }`. `source` and
  `urgency` are rendered as tags (urgent items get amber styling); `link`
  (optional) makes the summary clickable.

If the file is missing, empty, or fails to parse, the panel shows a clean
empty/error state — the app never crashes because of it.

## TickTick (new in v2)

Uses the TickTick Open API v1 (`https://api.ticktick.com/open/v1`) with a
personal access token, Bearer auth. The token is read from a read-only
mounted JSON file (`{"token": "..."}`), same pattern as the Google creds —
see `TICKTICK_TOKEN_PATH` in `.env`/`.env.example` and the
`ticktick_token.json` mount in `docker-compose.yml`.

`backend/app/ticktick_client.py` calls `GET /project` to list Simon's named
lists, then `GET /project/{id}/data` for each to get its tasks — **plus**
an explicit `GET /project/inbox/data` call. That's a deliberate deviation
from the literal "fetch all projects" reading: TickTick's `/project`
endpoint does not include the built-in Inbox list, and in practice nearly
all of Simon's real open tasks live there (46 of them, vs. 0 in his one
named project, confirmed against his real account) — so without the
explicit inbox fetch the panel would render almost empty. Tasks are
filtered to incomplete (`status != 2`), flattened, sorted by `dueDate`
ascending with no-due-date items last, and capped to 15 for display.
Overdue tasks get a red accent. Polled every ~2.5 minutes. On a 401 or
network error the panel shows a "TickTick unavailable" state rather than
crashing the app.

## Data sources & credentials

Read-only bind mounts only — nothing is copied into the image or committed:

- `google_token.json`, `google_client_secret.json` — Simon's existing
  Google OAuth token (already has a `refresh_token`; the backend loads and
  auto-refreshes it via `google-auth`, it never runs an OAuth flow).
- `dashboard_data` folder (triage snapshot).
- `ticktick_token.json` — TickTick personal access token, read-only.

If Gmail/Calendar auth fails or the token can't be refreshed, those two
panels show a "Gmail/Calendar unavailable" state with the error — the rest
of the dashboard keeps working. Same pattern for TickTick ("TickTick
unavailable").

## Stack

FastAPI + Uvicorn (single container), server-sent events for push updates,
plain HTML/CSS/vanilla JS frontend (no build step), Docker Compose.
