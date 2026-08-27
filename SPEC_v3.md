# PA Command Center — v3: Layout + Style Overhaul

Read the existing codebase first (backend/app/*, backend/static/*). This is
a visual/layout redesign only — data sources, API shape, SSE, ranking logic
all stay exactly as they are. Do not touch backend logic except item 0
below.

## 0. Remove OPEN LOOPS panel
Drop the Weekly Notes / OPEN LOOPS panel entirely (frontend + the backend
weekly_notes polling loop and /api/state field). Simon uses TickTick as his
real task system now; this panel was redundant and confusing ("what's an
item in Obsidian?"). Clean removal — no dead code, no dead mount if nothing
else needs the vault path (check main.py/docker-compose.yml/README before
ripping it out, remove the vault bind mount too if genuinely unused after
this change).

## 1. New visual direction: clean, bold, futuristic, pastel
Complete restyle — this replaces the "low-poly Y2K cyber-noir / liminal
gamecore" look entirely, not a variation on it. New direction:
- **Clean & bold**: generous whitespace, confident large type for headers,
  no clutter, no noise/grain/scanline textures, no moody darkness.
- **Thick lines**: bold 2-4px borders/dividers/strokes as a core visual
  motif — panels defined by strong outline rather than drop shadows or
  glow. Chunky, confident geometric shapes (rounded rects are fine, sharp
  corners are fine — pick one and be consistent).
- **Pastel palette**: soft mint/lavender/peach/sky-blue/butter-yellow
  tones, likely on a very light (near-white or very pale grey/cream)
  background OR alternatively a bold-but-soft dark base with pastel
  accents if that reads more "futuristic command center" — your call,
  but keep it light and airy rather than moody. Avoid neon/glow entirely.
  Use one pastel per panel/category as an accent (e.g. mint for
  calendar, lavender for signal/email, peach for tasks, sky-blue for
  focus) to help the eye parse sections at a glance.
- **Futuristic**: modern geometric sans-serif type (system font stack or a
  clean Google Font like "Space Grotesk", "Sora", or "Inter" — avoid pixel
  fonts and typewriter monospace now), maybe subtle rounded-corner
  iconography or simple geometric accent shapes (thick-stroke icons,
  circles/arcs used as decorative elements), crisp micro-animations
  (numbers ticking, smooth fade/slide on data updates, a subtle pulse on
  the live connection dot) rather than atmospheric background animation.
  Think: modern SaaS product dashboard (Linear, Stripe, Vercel-adjacent)
  crossed with a playful pastel edge — bold and clean, not corporate-grey.

## 2. Layout: make better use of space, avoid cramped scroll boxes
Current 2x2 grid + top FOCUS bar cramps real content (calendar has 6
items, triage 8, tasks 15, focus 5) into small scrolling boxes. Redesign
with a layout that actually fits this data:
- Consider an asymmetric/dashboard-grid layout rather than uniform equal
  panels: e.g. FOCUS as a prominent full-width strip or hero area at top
  (it's only ~5 items, give it room to breathe, not a tiny box); below,
  size panels by their real content volume — TASKS (up to 15 items) and
  SIGNAL (up to 8) need more vertical room than a small square; CALENDAR
  (6 items, timeline-shaped) suits a narrower tall column.
  A 12-column CSS grid with panels spanning different column/row counts
  (e.g. FOCUS spans 12 cols x short height at top; CALENDAR spans 4 cols x
  tall; TASKS spans 5 cols x tall; SIGNAL spans 3 cols x tall, or similar —
  use your judgement) will look much more considered than four equal
  boxes.
- It's fine for individual panels to internally scroll if content
  genuinely exceeds the viewport, but the goal is for panels to be sized
  to their typical content so scrolling is the exception not the norm at
  normal browser window sizes (assume viewing on a normal laptop screen,
  ~1440x900 minimum, could be larger on an external monitor — feel free to
  use a max-width centered layout or genuinely fill wide screens well).
- Keep header (wordmark, clock, connection status) and footer (per-source
  freshness) but restyle them to match the new pastel/bold look — the
  footer can be slimmer/more minimal now given fewer sources (no more
  weekly_notes row).

## 3. Definition of done
- Rebuild with `docker compose up -d --build`, verify container healthy
  and `/api/state` still returns real data for gmail, calendar, triage,
  ticktick, focus (no weekly_notes key anymore) via curl.
- Take a real screenshot (headless browser) and describe the new look in
  detail: colors used, panel arrangement, how FOCUS reads first, how
  TASKS/SIGNAL/CALENDAR are sized relative to their real content volume.
- Update README to reflect: panel removed, new style description, no
  vault mount if removed.
- Commit to git with a clear message.

Report back: exact new layout structure, exact palette (hex values used),
what changed in each file, and confirm real data still renders correctly
post-restyle.
