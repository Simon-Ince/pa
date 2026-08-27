"""TickTick Open API v1 client — read-only task fetch using Simon's personal
access token (Bearer auth). https://developer.ticktick.com/docs#/openapi
"""
import json
import logging
import os

import requests

logger = logging.getLogger("pa.ticktick")

TOKEN_FILE = os.environ.get("TICKTICK_TOKEN_FILE", "/secrets/ticktick_token.json")
BASE_URL = "https://api.ticktick.com/open/v1"
REQUEST_TIMEOUT = 10
COMPLETED_STATUS = 2


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


def fetch_open_tasks(max_items: int = 15) -> list[dict]:
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
            tasks.append(
                {
                    "id": t.get("id"),
                    "title": t.get("title") or "(untitled)",
                    "project": pname,
                    "due_date": t.get("dueDate"),
                    "priority": t.get("priority", 0),
                    "link": f"https://ticktick.com/webapp/#p/{pid}/tasks/{t.get('id')}",
                }
            )

    tasks.sort(key=lambda t: (t["due_date"] is None, t["due_date"] or ""))
    return tasks[:max_items]
