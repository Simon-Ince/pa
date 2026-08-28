# PA Command Center — v4: Bauhaus Restyle

Read the existing codebase first (backend/app/*, backend/static/*). This is
a full visual restyle only — replace the current pastel v3 look entirely.
Data sources, layout structure (FOCUS hero + CALENDAR/TASKS/SIGNAL grid),
SSE, and backend logic all stay as-is from v3 — only CSS/HTML visual
treatment changes, though you may adjust markup/classes as needed to
support the new component patterns below (e.g. corner decoration shapes,
geometric logo mark).

## Design system to apply: Bauhaus

Full spec below — apply it faithfully to THIS app's actual UI (a live data
dashboard with panels/cards/lists, not a marketing/landing page). Where the
spec describes marketing-page sections (hero, pricing, blog, testimonials,
final CTA) that don't apply here, translate the *underlying visual
language* (color blocking, hard shadows, thick borders, geometric shapes)
onto the dashboard's actual components: header/wordmark, FOCUS hero strip,
CALENDAR/TASKS/SIGNAL panels, list rows within panels, footer.

<design-system>
# Design Style: Bauhaus

## 1. Design Philosophy
The Bauhaus style embodies the revolutionary principle "form follows function" while celebrating pure geometric beauty and primary color theory. This is **constructivist modernism**—every element is deliberately composed from circles, squares, and triangles. The aesthetic should evoke 1920s Bauhaus posters: bold, asymmetric, architectural, and unapologetically graphic.

**Vibe**: Constructivist, Geometric, Modernist, Artistic-yet-Functional, Bold, Architectural

**Core Concept**: The interface is not merely a layout—it is a **geometric composition**. Every section is constructed rather than designed. Think of the page as a Bauhaus poster brought to life: shapes overlap, borders are thick and deliberate, colors are pure primaries (Red #D02020, Blue #1040C0, Yellow #F0C020), and everything is grounded by stark black (#121212) and clean white.

**Key Characteristics**:
- **Geometric Purity**: All decorative elements derive from circles, squares, and triangles
- **Hard Shadows**: 4px and 8px offset shadows (never soft/blurred) create depth through layering
- **Color Blocking**: Entire sections use solid primary colors as backgrounds
- **Thick Borders**: 2px and 4px black borders define every major element
- **Asymmetric Balance**: Grids are used but intentionally broken with overlapping elements
- **Constructivist Typography**: Massive uppercase headlines (text-6xl to text-8xl) with tight tracking
- **Functional Honesty**: No gradients, no subtle effects—everything is direct and declarative

## 2. Design Token System (The DNA)

### Colors (Single Palette - Light Mode)
The palette is strictly limited to the Bauhaus primaries, plus stark black and white.
-   `background`: `#F0F0F0` (Off-white canvas)
-   `foreground`: `#121212` (Stark Black)
-   `primary-red`: `#D02020` (Bauhaus Red)
-   `primary-blue`: `#1040C0` (Bauhaus Blue)
-   `primary-yellow`: `#F0C020` (Bauhaus Yellow)
-   `border`: `#121212` (Thick, distinct borders)
-   `muted`: `#E0E0E0`

### Typography
-   **Font Family**: **'Outfit'** (geometric sans-serif from Google Fonts). This typeface's circular letterforms and clean geometry perfectly embody Bauhaus principles.
-   **Font Import**: `Outfit:wght@400;500;700;900`
-   **Scaling**: Extreme contrast between display and body text
    -   Display: text-4xl (mobile) → text-6xl (tablet) → text-8xl (desktop)
    -   Subheadings: text-2xl → text-3xl → text-4xl
    -   Body: text-base → text-lg
-   **Weights**:
    -   Headlines: font-black (900) with uppercase and tracking-tighter
    -   Subheadings: font-bold (700) with uppercase
    -   Body: font-medium (500) for readability
    -   Labels: font-bold (700) with uppercase and tracking-widest
-   **Line Height**: Tight for headlines (leading-[0.9]), relaxed for body (leading-relaxed)

### Radius & Border
-   **Radius**: Binary extremes—either `rounded-none` (0px) for squares/rectangles or `rounded-full` (9999px) for circles. No in-between rounded corners.
-   **Border Widths**:
    -   Mobile: `border-2` (2px)
    -   Desktop: `border-4` (4px)
    -   Navigation/Major divisions: `border-b-4` (4px bottom border)
-   **Border Color**: Always `#121212` (black) for maximum contrast

### Shadows/Effects
-   **Hard Offset Shadows** (inspired by Bauhaus layering):
    -   Small: `shadow-[3px_3px_0px_0px_black]` or `shadow-[4px_4px_0px_0px_black]`
    -   Medium: `shadow-[6px_6px_0px_0px_black]`
    -   Large: `shadow-[8px_8px_0px_0px_black]`
-   **Button Press Effect**: `active:translate-x-[2px] active:translate-y-[2px] active:shadow-none` (simulates physical button press)
-   **Card Hover**: `hover:-translate-y-1` or `hover:-translate-y-2` (subtle lift)
-   **Patterns**: Use CSS background patterns for texture
    -   Dot grid: `radial-gradient(#fff 2px, transparent 2px)` with `background-size: 20px 20px`
    -   Opacity overlays: Large geometric shapes at 10-20% opacity for background decoration

## 3. Component Stylings

### Buttons / clickable elements (e.g. the SIGNAL unread-count link, item links)
-   **Variants**:
    -   **Primary** (Red): `bg-[#D02020] text-white border-2 border-black shadow-[4px_4px_0px_0px_black]`
    -   **Secondary** (Blue): `bg-[#1040C0] text-white border-2 border-black shadow-[4px_4px_0px_0px_black]`
    -   **Yellow**: `bg-[#F0C020] text-black border-2 border-black shadow-[4px_4px_0px_0px_black]`
    -   **Outline**: `bg-white text-black border-2 border-black shadow-[4px_4px_0px_0px_black]`
-   **Shapes**: Either `rounded-none` (square) or `rounded-full` (pill). Use shape variants deliberately.
-   **States**: Active/click = button "presses down" (translate + shadow removed).
-   **Typography**: Uppercase, font-bold, tracking-wider

### Cards (panels: FOCUS, CALENDAR, TASKS, SIGNAL; and list rows within them)
-   **Base Style**: White background, `border-4 border-black`, `shadow-[8px_8px_0px_0px_black]`
-   **Decoration**: Small geometric shape in top-right corner (8px-16px): circle/square/triangle in a primary color, rotate through the three shapes across the four panels so each panel has a distinct geometric identity marker (e.g. FOCUS=circle, CALENDAR=square, TASKS=triangle, SIGNAL=rotated square)
-   **Hover**: subtle lift effect on interactive rows
-   **Content Hierarchy**: Large bold titles, medium body text, generous padding
-   Individual list rows (calendar events, tasks, triage items, focus items) should themselves read as smaller nested Bauhaus blocks: thinner border (2px), small color-blocked tag/badge for urgency or source (using the primary palette), not just plain text rows.

## 4. Layout & Spacing
-   **Container Width**: generous max-width, poster-like breadth, centered on very wide screens
-   **Section Padding**: generous — 16-24px mobile scaling to 32px+ desktop
-   **Grid Systems**: keep the v3 asymmetric structure (FOCUS full-width hero at top, then CALENDAR/TASKS/SIGNAL sized to content below) but apply Bauhaus color-blocking and hard-shadow card treatment to each
-   **Spacing Scale**: Consistent 4/8/12/16/24px
-   **Section Dividers**: strong `border-b-4 border-black` under the header

## 5. Non-Genericness (Bold Choices) — MANDATORY
-   **Color Blocking**: assign one Bauhaus primary as a strong color-blocked background to each major panel or its header strip, e.g. FOCUS header strip = solid blue, CALENDAR header strip = solid yellow, TASKS header strip = solid red, SIGNAL header strip = white/outline — rotate deliberately so the page reads as a genuine color composition, not uniform white cards.
-   **Geometric Logo**: the "PA COMMAND CENTER" wordmark in the header should be accompanied by a small geometric mark built from a circle + square + triangle in the three primaries, Bauhaus-poster style — this is the app's identity mark.
-   **Geometric Compositions**: add a decorative geometric composition (overlapping circle/rotated square/triangle at low opacity, e.g. 10-20%) somewhere in the header or FOCUS hero background for visual interest, in the Bauhaus poster spirit — kept subtle enough not to reduce data legibility.
-   **Rotated Elements**: deliberate 45° rotation on at least one recurring decorative element (e.g. every corner-decoration square, or the small badge shapes).
-   **Unique Decorations**: small 8-16px geometric shapes rotating through the three primaries as accents on card corners.

## 6. Icons & Imagery
-   Prefer simple geometric shape-based accents (circle/square/triangle) over any icon library import — keep the frontend dependency-free (no npm icon package; this is plain HTML/CSS/JS with no build step). Build icons as small inline SVGs or CSS shapes.
-   Stroke width 2-3px where SVG strokes are used.

## 7. Responsive Strategy
-   Mobile-first still relevant since Simon may check this on other devices later: single column below ~700px, the v3 grid breakpoint logic can stay, just re-themed. Scale border widths down slightly on narrow viewports (4px → 2px) and shadow offsets down proportionally (8px → 4px) per the spec.

## 8. Animation & Micro-Interactions
-   Feel: mechanical, snappy, geometric — NOT the soft fade-ins from v3. Fast `duration-200`/`duration-300`, `ease-out`. New SSE data arriving can still use a fast slide/snap-in rather than a soft fade. Live connection dot can be a small solid circle with a snappy pulse (opacity or scale step, not a soft glow blur). No soft glow, no scanline, no organic drift.
</design-system>

## Definition of done
- Rebuild with `docker compose up -d --build`, verify container healthy and
  `/api/state` still returns real data for gmail, calendar, triage,
  ticktick, focus via curl (same 5 keys as v3, no regressions).
- Take a real screenshot (headless browser, ~1440x900) and describe the
  result in detail: confirm color-blocked panel headers, thick black
  borders, hard offset shadows, the geometric logo mark, Outfit font
  loading, and that real live data (actual task titles, actual calendar
  events, actual triage items) is legible and correctly styled — not
  placeholder content.
- Update README to note the style is now "Bauhaus / constructivist
  modernism" instead of pastel-futurist.
- Commit to git with a clear message.

Report back: what changed per file, exact palette/tokens applied (confirm
you used the exact hex values given, not approximations), and confirm real
data renders correctly post-restyle with the screenshot description.
