# PA Command Center — v2 Redesign Brief

This supersedes parts of the original SPEC.md build. Read the existing
codebase in this repo first (backend/app/*, backend/static/*) — this is an
iteration, not a rebuild from scratch. Keep the FastAPI + SSE + Docker
Compose architecture. Visual style stays as currently implemented (the
low-poly Y2K cyber-noir / liminal gamecore reskin already committed) —
no style changes in this pass, this is a content/data redesign.

## Why this pass

Simon's feedback on v1: the calendar panel showed "Home"/"Office" working-
location entries as if they were meetings (they're not — they're all-day
location markers). The raw unread-Gmail list panel wasn't useful — he'd
rather just open Gmail himself for that; what he actually wants is a small
count of untriaged messages plus only what's genuinely important, based on
the existing triage cron's judgement (not naive unread-ness). He also wants
his TickTick todos in here. And the overarching ask: this should be a
"one-stop shop that cuts through the noise and guides my focus" — not four
disconnected raw-data panels.

## Required changes

### 1. Calendar panel: filter out all-day / working-location entries
Google Calendar events that are all-day (`start.date` present, no
`start.dateTime`) and/or match common working-location patterns (summary
in a small denylist: "Home", "Office", "Working from home", "WFH", or any
event where Google's `eventType` is `workingLocation` — the Calendar API
does return `eventType: "workingLocation"` for these, prefer checking that
field over string matching if present in the raw API response researched
before you build). Only show real timed meetings. If filtering removes an
event and it's the type note it in code comments so it's easy to adjust
later.

### 2. Gmail panel replacement: count + triage-flagged items only
Remove the raw unread-email list. Replace with:
- A prominent untriaged/unread count (from live Gmail `is:unread` count,
  same query as before minus the full item list — just the count is fine,
  cheap to compute).
- Below it, the "important" items sourced from the triage cron's JSON
  snapshot: /Users/simonince/.hermes/profiles/pa/dashboard_data/triage_snapshot.json
  (same mount as before, already wired). That file now has this shape
  (confirm by reading the actual file, it should exist after this cron
  run: `{"generated_at","channel","unread_count","items":[{"summary",
  "source":"gmail|chat|whatsapp","urgency":"urgent|reply|action|waiting",
  "link"}]}`). Render each item with its source icon/tag and urgency
  styling (urgent items visually distinct — e.g. brighter/amber accent).
  If the snapshot is stale (generated_at older than ~7 hours during work
  hours) show a subtle "stale" indicator, don't hide the data.
  Rename this panel something like "SIGNAL" or "PRIORITY QUEUE" rather
  than "Inbox Queue" since it's not raw inbox anymore.

### 3. New panel: TickTick todos
TickTick Open API v1, base URL `https://api.ticktick.com/open/v1`. Personal
access token (Bearer auth) mounted read-only at
`/Users/simonince/.hermes/profiles/pa/ticktick_token.json` -> `/secrets/ticktick_token.json:ro`
in compose (JSON shape: `{"token": "..."}` — read the `token` field, send
as `Authorization: Bearer <token>`).
Endpoints: `GET /project` lists projects/lists; `GET /project/{id}/data`
returns that project's tasks. Fetch all projects, then each project's
tasks, filter to incomplete tasks only (status != 2, i.e. not completed),
flatten into one list, sort by due date (`dueDate` field) ascending with
no-due-date items last, cap to a reasonable count (~15) for display. Show
title, project name, due date if present (highlight overdue in a warning
color), priority if set. Poll every ~2-3 min (todos don't need SSE-fast
refresh). Handle API errors gracefully (401/network) — show "TickTick
unavailable" state, don't crash the app. New panel title e.g. "TASKS" or
"TODO".

### 4. New top panel: FOCUS — the organizing idea
Add a fifth panel, positioned first/most prominent (top of the page,
full-width above the grid, or top-left with visual priority — your call on
layout but it must read first). This is a synthesized "what should I
actually focus on" list of 3-5 items, computed server-side by combining
signal from: the triage snapshot's urgent/reply items, today's remaining
calendar meetings (esp. anything starting soon), overdue or due-today
TickTick tasks, and open checkbox items from today's Weekly Notes day
section specifically (not the whole week — just today's day heading).
This is NOT an LLM call from the backend (keep the app dependency-free of
LLM APIs) — implement it as clear, inspectable ranking/heuristic logic in
Python: e.g. rank by (urgent triage items) > (meeting starting within next
60 min) > (overdue tasks) > (due-today tasks) > (today's open weekly-note
items) > (reply-needed triage items), cap at 5, dedupe similar entries.
Label each focus item with which source it came from (small tag: MEETING /
TASK / SIGNAL / NOTES) so it's traceable, not a black box. If nothing
qualifies, show "Nothing urgent — clear to focus" rather than an empty box.

### 5. Layout
Reasonable revised layout: FOCUS panel full-width at top. Below it, a grid
with TODAY/TOMORROW (filtered calendar), SIGNAL (triage count+items),
TASKS (TickTick), OPEN LOOPS (weekly notes, keep as-is). Keep the header
(clock, connection status) and footer (per-source freshness) as-is, add
TickTick to the footer's freshness row.

## Non-functional
- No new secrets in git; ticktick_token.json mounted read-only like the
  Google credentials.
- Update README.md: describe the new FOCUS panel's ranking logic in plain
  terms, the new TickTick data source and its env/mount requirements, the
  changed Gmail panel behavior, and the calendar filter behavior.
- Update .env.example if any new path needs configuring.
- Rebuild with `docker compose up -d --build`, verify with curl that
  `/api/state` now includes real ticktick data (actual task titles from
  Simon's account), a real focus list, a filtered calendar (confirm no
  "Home"/"Office" entries appear if any existed in the raw fetch — check
  by comparing raw vs filtered counts in your verification, don't just
  trust the code), and the triage snapshot data if the file exists by the
  time you build (it should — a manual cron run was triggered before this
  task started; if the file still isn't there after a few minutes wait
  and check again, and if it's genuinely still missing after that, verify
  your empty-state renders cleanly and note this in your final report
  rather than blocking on it).
- Take a screenshot to confirm the new layout visually reads well (FOCUS
  panel prominent, everything else legible) and describe it in your report.
- Commit to git with a clear message once verified.

Report back: what changed, real data verification results (paste actual
counts/values you confirmed), any deviations and why.
