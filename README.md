# PA Command Center

A self-hosted, always-on personal dashboard for Simon. One FastAPI service
serves both the API and a plain HTML/CSS/JS frontend — Bauhaus /
constructivist modernism (v4): primary color-blocking, thick black borders,
hard offset shadows, geometric shapes — pulling from Gmail, Google
Calendar, a message-triage cron snapshot, and TickTick.

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
(scanlines, noise, grain, ambient canvas dust/facets, pixel font) was
replaced with a clean, bold, pastel design (near-white canvas, thick
3px black borders, rounded corners, Space Grotesk + Inter, one pastel
wash/deep accent per panel). Superseded by v4 below.

## v4: Bauhaus / constructivist modernism restyle

The v3 pastel look has been replaced entirely with a Bauhaus /
constructivist-modernism treatment — same data sources, layout structure
(FOCUS hero + CALENDAR/TASKS/SIGNAL grid), SSE, and backend logic, only the
visual language changed:

- **Palette** — strict primaries plus stark black/white, no gradients, no
  pastels: background `#F0F0F0`, foreground/border `#121212`, red
  `#D02020`, blue `#1040C0`, yellow `#F0C020`, muted `#E0E0E0`.
- **Type**: Outfit (geometric sans, weights 400/500/700/900) everywhere,
  replacing Space Grotesk + Inter. Headlines are uppercase font-black.
- **Borders & shadows**: binary radius (square `0` or full `9999px` pills,
  nothing in between). 4px black borders on panels (2px on nested row
  cards), hard offset box-shadows (`8px 8px 0 0 #121212` on panels, down to
  `4px 4px` on badges) — no blur, no glow.
- **Color-blocked panel headers**, rotated deliberately so the page reads
  as a composition rather than uniform white cards: FOCUS = solid blue
  header strip, CALENDAR = solid yellow, TASKS = solid red, SIGNAL =
  white/outline.
  - Each panel also carries a distinct geometric corner marker (top-right):
    FOCUS = circle (red), CALENDAR = square (blue), TASKS = triangle
    (yellow), SIGNAL = rotated square/diamond (red).
- **Geometric logo mark**: a small square + circle + triangle composition
  in the three primaries sits beside the "PA COMMAND CENTER" wordmark in
  the header — the app's identity mark, built as inline SVG (no icon
  library; dependency-free frontend, as before).
- **Decorative composition**: a low-opacity (12–15%) overlapping circle and
  rotated square sit fixed behind the top-right of the page, Bauhaus-poster
  style, kept subtle enough not to reduce data legibility.
- **Row-level treatment**: list rows (calendar events, tasks, triage items,
  focus items) are nested Bauhaus blocks with 2px borders and small
  color-blocked, uppercase badges for source/urgency/priority (e.g. the
  `urgent` triage badge and overdue task rows flip to a solid red block).
- **Motion**: mechanical and snappy, not soft — a stepped (non-easing)
  pulse on the live connection dot instead of a soft glow, and a fast
  (`0.2s ease-out`) slide/snap-in on new SSE-rendered rows instead of a
  gentle fade.
- **Responsive**: border widths and shadow offsets scale down (4px → 2px,
  8px → 4px) below 640px; the v3 single-column breakpoint logic below
  1100px is unchanged.

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
