"""TickTick Open API v1 client — read-only task fetch using Simon's personal
access token (Bearer auth). https://developer.ticktick.com/docs#/openapi
"""
import json
import logging
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger("pa.ticktick")

TOKEN_FILE = os.environ.get("TICKTICK_TOKEN_FILE", "/secrets/ticktick_token.json")
BASE_URL = "https://api.ticktick.com/open/v1"
REQUEST_TIMEOUT = 10
COMPLETED_STATUS = 2
DISPLAY_CAP = 15
LOCAL_TZ = ZoneInfo("Europe/London")

# TickTick titles often embed markdown, typically an Obsidian Inbox link:
#   "Get bike rack [Inbox.md](obsidian://open?vault=...)"
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


class TickTickAuthError(Exception):
    pass


def _load_token() -> str:
    if not os.path.exists(TOKEN_FILE):
        raise TickTickAuthError(f"token file not found at {TOKEN_FILE}")
    with open(TOKEN_FILE, encoding="utf-8") as f:
        info = json.load(f)
    token = info.get("token")
    if not token:
        raise TickTickAuthError("token file has no 'token' field")
    return token


def _get(path: str, headers: dict):
    try:
        resp = requests.get(f"{BASE_URL}{path}", headers=headers, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        raise TickTickAuthError(f"network error calling {path}: {e}") from e
    if resp.status_code == 401:
        raise TickTickAuthError("TickTick token rejected (401)")
    resp.raise_for_status()
    return resp.json()


def parse_task_title(raw: str) -> tuple[str, str | None]:
    """Strip markdown links from a TickTick title.

    Obsidian `obsidian://` URLs become `note_link`. Other markdown links are
    replaced with their label text so the human title remains readable.
    """
    if not raw:
        return "(untitled)", None
    note_link = None

    def repl(match: re.Match) -> str:
        nonlocal note_link
        label, url = match.group(1), match.group(2)
        if url.startswith("obsidian://") and not note_link:
            note_link = url
            return ""
        return label or ""

    title = MARKDOWN_LINK_RE.sub(repl, raw)
    title = re.sub(r"\s+", " ", title).strip(" -:·")
    return title or "(untitled)", note_link


def _parse_due(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        v = value.strip()
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        if len(v) >= 5 and v[-5] in "+-" and v[-3] != ":":
            v = v[:-2] + ":" + v[-2:]
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _bucket(due: datetime | None, today_local) -> str:
    if due is None:
        return "later"
    due_local = due.astimezone(LOCAL_TZ).date()
    if due_local < today_local:
        return "overdue"
    if due_local == today_local:
        return "today"
    return "later"


def fetch_open_tasks() -> dict:
    """Fetch all incomplete tasks, then return a curated payload.

    `items` is overdue + due-today only (capped at DISPLAY_CAP). Tasks due
    later or with no due date are counted in `later_count`, not listed.
    """
    token = _load_token()
    headers = {"Authorization": f"Bearer {token}"}

    projects = _get("/project", headers)
    # GET /project does not include the built-in Inbox (confirmed against
    # Simon's real account: /project returned only his one named list, while
    # nearly all of his actual open tasks live in Inbox). TickTick's Open
    # API supports the special project id "inbox" for that list even though
    # it's undocumented in /project's own response — fetch it explicitly so
    # the panel isn't silently missing most of his todos.
    project_specs = [("inbox", "Inbox")] + [
        (p.get("id"), p.get("name", "(unnamed)")) for p in projects if p.get("id")
    ]

    tasks = []
    for pid, pname in project_specs:
        try:
            data = _get(f"/project/{pid}/data", headers)
        except TickTickAuthError:
            raise
        except Exception as e:
            logger.warning("ticktick: failed to fetch project %s data: %s", pid, e)
            continue
        for t in data.get("tasks", []):
            if t.get("status") == COMPLETED_STATUS:
                continue
            raw_title = t.get("title") or "(untitled)"
            title, note_link = parse_task_title(raw_title)
            tasks.append(
                {
                    "id": t.get("id"),
                    "title": title,
                    "project": pname,
                    "due_date": t.get("dueDate"),
                    "priority": t.get("priority", 0),
                    "link": f"https://ticktick.com/webapp/#p/{pid}/tasks/{t.get('id')}",
                    "note_link": note_link,
                }
            )

    today_local = datetime.now(LOCAL_TZ).date()
    overdue, due_today, later = [], [], []
    for t in tasks:
        bucket = _bucket(_parse_due(t.get("due_date")), today_local)
        if bucket == "overdue":
            overdue.append(t)
        elif bucket == "today":
            due_today.append(t)
        else:
            later.append(t)

    def sort_due(items: list[dict]) -> list[dict]:
        return sorted(items, key=lambda t: (t["due_date"] is None, t["due_date"] or ""))

    curated = sort_due(overdue) + sort_due(due_today)
    more_count = max(0, len(curated) - DISPLAY_CAP)

    return {
        "items": curated[:DISPLAY_CAP],
        "later_count": len(later),
        "open_count": len(tasks),
        "more_count": more_count,
    }
