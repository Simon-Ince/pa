"""Parses the current week's Obsidian Weekly Note for open (unchecked) items,
grouped by the Mon-Fri day heading they fall under.
"""
import os
import re
from datetime import date, timedelta

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

HEADING_RE = re.compile(
    r"^#{1,6}\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b",
    re.IGNORECASE,
)
ANY_HEADING_RE = re.compile(r"^#{1,6}\s+")
CHECKBOX_RE = re.compile(r"^-\s*\[ \]\s*(.+)$")
TICKTICK_META_RE = re.compile(r"%%.*?%%")


def current_week_monday(today: date | None = None) -> date:
    d = today or date.today()
    return d - timedelta(days=d.weekday())


def find_current_week_note(vault_dir: str) -> tuple[str | None, date]:
    monday = current_week_monday()
    filename = f"Weekly Notes {monday.strftime('%d-%m-%y')}.md"
    path = os.path.join(vault_dir, filename)
    if os.path.isfile(path):
        return path, monday
    return None, monday


def _clean_item_text(text: str) -> str:
    text = TICKTICK_META_RE.sub("", text)
    return text.strip()


def parse_open_items(path: str) -> dict:
    days = {d: [] for d in DAY_NAMES}
    current_day = None
    with open(path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            day_match = HEADING_RE.match(line)
            if day_match:
                name = day_match.group(1).capitalize()
                current_day = name if name in days else None
                continue
            if ANY_HEADING_RE.match(line):
                current_day = None
                continue
            cb_match = CHECKBOX_RE.match(line)
            if cb_match and current_day:
                text = _clean_item_text(cb_match.group(1))
                if text:
                    days[current_day].append(text)
    return days
