# PA Command Center

A self-hosted, always-on personal dashboard for Simon. One FastAPI service
serves both the API and a plain HTML/CSS/JS frontend — Swiss International
Typographic Style (v5): Inter, black/white/Swiss red, a visible grid, no
shadows — pulling from Gmail, Google Calendar, a message-triage cron
snapshot, and TickTick.

## Run it

```bash
cp .env.example .env   # adjust paths only if yours differ from the defaults
docker compose up -d --build
```

Then open **http://localhost:8420**. Theme toggle (square in the header) switches
light/dark; choice is stored in `localStorage`. First visit follows the OS
preference. Dark mode is a black canvas, charcoal panels, light type,
white rules, and Swiss red for signal — not inverted white cards.

Stop it:

```bash
docker compose down
```

Logs:

```bash
docker compose logs -f
```

## How Hermes Agent fits

This repo is a **read-only command centre**. It does not run triage, send
Slack messages, draft replies, or write notes. Hermes Agent (the `pa`
profile) is the thing that does that work. The dashboard mounts Hermes's
existing files and displays them.

```
Hermes (cron / Slack)          this dashboard
---------------------          --------------
message triage  ──writes──►  dashboard_data/triage_snapshot.json
Google OAuth token  ─ro──►  Gmail unread count + Calendar
TickTick token      ─ro──►  Tasks
```

**Triage snapshot path** (what Hermes should write):

`/Users/simonince/.hermes/profiles/pa/dashboard_data/triage_snapshot.json`

That folder is `DASHBOARD_DATA_PATH` in `.env`, bind-mounted read-only into
the container as `/data`. The dashboard polls it every ~90s. Shape is in
"Triage snapshot contract" below. `generated_at` drives the STALE flag
(shown on weekdays 8am–6pm if the file is older than ~7 hours) and the
Gmail "unread since last triage" window.

**SIGNAL** is two layers:

1. The **list** — `items` from that snapshot. Those are the messages/chats
   Hermes already judged worth surfacing (`gmail` / `chat` / etc, with
   `urgent` / `reply` / `action` / `waiting`). Not a raw inbox.
2. The **header count** — live Gmail unread *since* `generated_at`, fetched
   by this app. It is not the snapshot's `unread_count` field.

FOCUS pulls `urgent` and `reply` items from the same snapshot. Calendar and
TickTick are live API reads using the same tokens Hermes already has;
Hermes does not need to dump those into the snapshot.

## What each panel shows

- **DECIDE** — full-width hero on Today. The morning brief's `decisions`
  array (`decide` and `reply`, then any `waiting`), each row the action,
  why, and a link. This is the judgment the brief agent already made.
  `fyi` is not shown. The older FOCUS heuristic still runs in the API and
  is not on the page.
- **SLACK / LINEAR** — technology-side digests (`slack_digest.json`,
  `linear_digest.json`). Today shows Slack as-is and the Linear items that
  need Simon, are blocked, or are at risk, plus each team's active /
  blocked / shipped counts. The Technology tab shows the full Linear list,
  including shipped and started, and the team notes. A quiet Slack window
  ("nothing new") is a healthy empty digest, not an error.
- **TODAY / TOMORROW** — Calendar events from now through the end of
  tomorrow, with all-day "working location" markers filtered out (see
  below). Each event includes `start` and `end`. The list is split into
  Today / Tomorrow. Timed events whose intervals overlap are clustered as
  one block with an `OVERLAP` badge (side-by-side lanes when they fit),
  each showing a time range (`14:50–18:00`) rather than two sequential
  `NOW` cards. In-progress events show "ends in Xm"; upcoming events show
  "starts in Xm" — the old "still NOW for 60 minutes after start" rule is
  gone. In-progress clusters (or the next upcoming, if nothing is in
  progress) are inverted (black fill, white type). Polled every ~60s.
- **SIGNAL** — the body is the items the existing "Simon message triage"
  cron judged worth surfacing, read from its JSON snapshot (see contract
  below). The live Gmail unread count sits as a small chip in the panel
  header (clickable through to the exact Gmail search), not a giant
  billboard. The count is unread primary inbox mail since the last triage
  run. Gmail's `after:{unix}` operator returns 0 when combined with
  `-category:` filters, so the query uses `newer_than:{N}h` (rounded up
  from `generated_at`, plus a one-hour buffer). If `generated_at` is
  missing or in the future it falls back to `newer_than:3d`. Counted by
  paging message IDs, not `resultSizeEstimate`. Each item shows its source (`gmail`/`chat`/etc) and
  urgency; `urgent` items get a red geometric marker and badge, not a
  full-row fill. If the snapshot is more than ~7 hours old *and* it's
  currently a weekday between 8am and 6pm, a "STALE" flag appears next
  to it (the data itself is still shown, never hidden).
- **TASKS** — overdue and due-today TickTick to-dos, grouped under those
  labels, plus a quiet `+N later` count for everything else (future due
  date or no due date). Titles have markdown/Obsidian links stripped to
  human text. Overdue is a small red square + red date, not a solid red
  card. See the TickTick section below for the data contract and one
  non-obvious API quirk. Polled every ~2.5 minutes (no need for SSE-fast
  refresh on todos).
- **TODAY'S NOTE** — today's section of the current Obsidian weekly note
  (`vault_notes.json`, written by Hermes). Prose, not a list.
- **DAILY BRIEF** — the morning brief (`daily_brief.json`): flagged
  highlights, optional audio, then the summary as readable paragraphs.
- **RECENT MEETINGS** — last few meetings with attendees, plus whether a
  transcript / write-up exists (`recent_meetings.json`).
- **ACTIVE PROJECTS** — tracked project notes from the vault snapshot
  (`vault_notes.json` `projects`).
- **ONLINE PRESENCE** — last posted item and pending drafts
  (`online_presence.json`).
- **TRIAGE PIPELINE** — Tier 1 / Tier 2 cron health (last run, next run,
  failing flag) from `pipeline_status.json`. System status, not work.

**v6: tabs.** The app outgrew a single page, so panels now live on six
hash-routed tabs (bookmarkable, keys 1–6 switch). One page is visible at a
time; each scrolls as one document with content-height panels.

1. **Today** (`#today`) — DECIDE, then SLACK / LINEAR, then CALENDAR /
   TASKS / SIGNAL. The default landing page.
2. **Brief** (`#brief`) — DAILY BRIEF (audio and transcript; the decision
   list is not repeated here when `decisions` is present) and TODAY'S NOTE.
3. **Technology** (`#technology`) — full Slack digest and full Linear
   digest.
4. **Meetings** (`#meetings`) — RECENT MEETINGS full width, each with
   Obsidian links to the notes it was logged in.
5. **Projects** (`#projects`) — ACTIVE PROJECTS (8, all of them, names
   open in Obsidian) and ONLINE PRESENCE (4).
6. **System** (`#system`) — TRIAGE PIPELINE and FEED HEALTH, which checks
   every feed's own timestamp against a max age and flags stale/missing
   ones. Slack and Linear digests go stale after 20 hours.

Tab badges summarise the hidden pages: decide/reply count on Today (red if
any are `decide`), "new" on Brief when today's brief exists, Slack and
Linear items that need Simon or are blocked/incidents on Technology,
transcripts not yet logged on Meetings, pending drafts on Projects, "!" on
System when any feed is unhealthy. Below 1100px panels stack and the tab
bar scrolls horizontally.

Footer shows per-source freshness: inbox/calendar/tasks are when this
app last polled those APIs; **triage is `generated_at`** (when the triage
run wrote the snapshot), not when the dashboard last reread the file. An
amber "RECONNECTING…" flag appears if the SSE connection drops
(`EventSource` auto-reconnects).

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
  color-blocked, uppercase badges for source/urgency/priority. Emphasis
  uses 8px geometric markers (red square for overdue/urgent) rather than
  painting the whole row. Yellow fill is reserved for "now" / next-up
  calendar blocks. FOCUS rank is a numbered square rotating yellow / blue /
  red.
- **Motion**: mechanical and snappy, not soft — a stepped (non-easing)
  pulse on the live connection dot instead of a soft glow, and a fast
  (`0.2s ease-out`) slide/snap-in on new SSE-rendered rows instead of a
  gentle fade.
- **Responsive**: border widths and shadow offsets scale down (4px → 2px,
  8px → 4px) below 640px; the v3 single-column breakpoint logic below
  1100px is unchanged.

Superseded by v5 below.

## v5: Swiss International Typographic Style

The v4 Bauhaus treatment (primaries, hard offset shadows, color-blocked
headers, geometric corner marks, Outfit) has been replaced with Swiss
International Style — same data sources, panel layout, SSE, and backend
logic; only the visual language changed:

- **Palette** — white `#FFFFFF`, black `#000000`, muted `#F2F2F2`, and a
  single accent **Swiss red `#FF3000`**. Red is a signal (urgent, overdue,
  STALE, reconnecting, rank 1, section indices), not decoration.
- **Type**: Inter (400/500/700/900). Headings and labels uppercase. Flush
  left. No Outfit.
- **Structure**: 4px black borders, `border-radius: 0`, **no drop
  shadows**. Each panel is a framed block with a muted header strip and
  gutters between sections so they don't read as one white field.
  Numbered section labels (`01`–`10`) in red. Page scrolls; panels are
  content-height. Now / Briefing / Context bands replace the old
  viewport-locked nested-scroll grid.
- **Texture**: 24px grid on the page, 16px dot matrix on SIGNAL, a faint
  noise overlay on the light canvas (not on dark).
- **Now/next** calendar rows invert to black fill / white type rather than
  yellow. Overdue/urgent use a 4px red leading rule.
- **Header**: no product title — clock, theme toggle, and connection
  status only.
- **Dark mode**: black canvas, charcoal panels (`#141414`), light type,
  white rules, same red accent. Not inverted white cards.

Landing-page scale from the style brief (`text-9xl`, lucide-react, full
card hover-to-red) is intentionally not applied — this is a glance
dashboard, not a marketing page.

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

Each event in `/api/state` also carries `end` (same `dateTime`/`date`
shape as `start`). The frontend uses that to detect overlapping timed
events and to show in-progress "ends in Xm" countdowns.

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
  `urgency` are rendered as tags; `urgent` items get a red geometric
  marker and badge. `link` (optional) makes the whole row clickable.
  When Hermes omits `link` for a `gmail` item, the dashboard looks up the
  thread via the Gmail API (short proper-noun query, not the full
  paraphrase) and opens `?fs=1#all/{threadId}` with `authuser` set to the
  token's mailbox. Gmail links are opened via an `about:blank` navigation
  so a new tab doesn't render Gmail's blank SPA. Chat/other sources stay
  unlinked until Hermes writes a real URL.

If the file is missing, empty, or fails to parse, the panel shows a clean
empty/error state — the app never crashes because of it.

## Slack and Linear digests

Same folder, same read-only mount. Each file degrades on its own.

`slack_digest.json`: `generated_at`, `status` (`ok` / `empty` / `error`),
`window`, `items[]` of `{ id, kind, title, summary, action, needs_simon,
channel, who, when, link }`. `kind` is `incident`, `decision`, `blocker`,
`ask`, or `fyi`. An `ok` file with an empty `items` array is a quiet
window, not a failure.

`linear_digest.json`: `generated_at`, `status`, `items[]` of `{ id, kind,
team, title, summary, action, needs_simon, state, assignee, updated, link }`,
and `teams[]` of `{ name, in_progress, blocked, shipped_since_yesterday,
note }`. `kind` is `needs_simon`, `blocked`, `shipped`, `started`, or
`at_risk`.

`daily_brief.json` may also include `decisions[]` of `{ id, kind, title,
action, why, when, source, link }`. `kind` is `decide`, `reply`, `waiting`,
or `fyi`. Today renders `decide`, `reply`, and `waiting`.

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
filtered to incomplete (`status != 2`), flattened, and sorted by `dueDate`
ascending with no-due-date items last. Titles that embed markdown
(typically `[Inbox.md](obsidian://…)`) are parsed: the human text is the
`title`, an `obsidian://` URL becomes `note_link`, and the TickTick web
URL stays on `link`.

The TASKS panel is curated rather than a dump of the inbox: `items` is
overdue + due-today only (capped at 15, with `more_count` if that set is
larger), `later_count` is everything else (future due date or none), and
`open_count` is the total incomplete. Overdue rows get a red geometric
marker, not a full-row fill. Polled every ~2.5 minutes. On a 401 or
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
