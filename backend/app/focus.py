"""Computes the FOCUS panel: a small, ranked "what to actually look at right
now" list, synthesized server-side from the other data sources. Deliberately
a plain heuristic, not an LLM call — every ranking decision here is
inspectable Python, not a black box.

Rank order (highest first), capped at MAX_ITEMS, deduped by lowercased text:
  1. triage items flagged urgent
  2. calendar meetings starting within MEETING_SOON_MINUTES
  3. overdue TickTick tasks
  4. TickTick tasks due today
  5. triage items flagged as needing a reply
"""
from datetime import datetime, timezone

MAX_ITEMS = 5
MEETING_SOON_MINUTES = 60


def _parse_iso(value):
    if not value:
        return None
    try:
        v = value.strip()
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        # TickTick uses +0000 / -0500 without a colon
        if len(v) >= 5 and v[-5] in "+-" and v[-3] != ":":
            v = v[:-2] + ":" + v[-2:]
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def compute_focus(triage: dict, calendar: dict, ticktick: dict, now: datetime, tz) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()

    def add(text: str, source: str, detail: str | None = None, link: str | None = None):
        key = (text or "").strip().lower()
        if not key or key in seen:
            return
        seen.add(key)
        items.append({"text": text.strip(), "source": source, "detail": detail, "link": link})

    triage_items = (triage or {}).get("items") or []
    calendar_items = (calendar or {}).get("items") or []
    ticktick_items = (ticktick or {}).get("items") or []

    # 1. urgent triage items
    for it in triage_items:
        if it.get("urgency") == "urgent":
            add(it.get("summary", ""), "SIGNAL", detail=it.get("source"), link=it.get("link"))

    # 2. meetings starting within the next hour
    for ev in calendar_items:
        if ev.get("all_day"):
            continue
        start = _parse_iso(ev.get("start"))
        if not start:
            continue
        mins = (start - now).total_seconds() / 60
        if 0 <= mins <= MEETING_SOON_MINUTES:
            add(
                ev.get("title", ""),
                "MEETING",
                detail=f"starts in {int(mins)}m",
                link=ev.get("meet_link") or ev.get("html_link"),
            )

    today_local = now.astimezone(tz).date()

    overdue, due_today = [], []
    for t in ticktick_items:
        due = _parse_iso(t.get("due_date"))
        if not due:
            continue
        due_local = due.astimezone(tz).date()
        if due_local < today_local:
            overdue.append(t)
        elif due_local == today_local:
            due_today.append(t)

    # 3. overdue tasks
    for t in overdue:
        add(t.get("title", ""), "TASK", detail="overdue", link=t.get("link"))

    # 4. due-today tasks
    for t in due_today:
        add(t.get("title", ""), "TASK", detail="due today", link=t.get("link"))

    # 5. reply-needed triage items
    for it in triage_items:
        if it.get("urgency") == "reply":
            add(it.get("summary", ""), "SIGNAL", detail=it.get("source"), link=it.get("link"))

    return items[:MAX_ITEMS]
