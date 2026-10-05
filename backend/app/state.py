"""Aggregates the four data sources into one small JSON state object, polls
them in the background, and fans out updates to SSE subscribers.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import focus as focus_module
from . import ticktick_client
from .google_client import (
    CredentialsHolder,
    GoogleAuthError,
    fetch_calendar_events,
    fetch_gmail_unread_count,
    gmail_ui_search_url,
    gmail_keyword_query,
    cached_gmail_thread_url,
    resolve_triage_gmail_links,
)

logger = logging.getLogger("pa.state")

GMAIL_POLL_SECONDS = 50
CALENDAR_POLL_SECONDS = 60
TRIAGE_POLL_SECONDS = 90
TICKTICK_POLL_SECONDS = 150
FOCUS_POLL_SECONDS = 20
HEARTBEAT_SECONDS = 25

TRIAGE_DATA_DIR = os.environ.get("TRIAGE_DATA_DIR", "/data")

LOCAL_TZ = ZoneInfo("Europe/London")
# Message-triage cron (Hermes pa job 1d71c046b9ad) runs weekdays at these local times.
TRIAGE_RUN_TIMES = [(6, 45), (12, 45)]
TRIAGE_GRACE = timedelta(minutes=45)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_section(status: str) -> dict:
    return {"status": status, "last_updated": None}


class AppState:
    def __init__(self):
        self.data = {
            "gmail": {
                "status": "pending",
                "unread_count": None,
                "count_window": None,
                "query": None,
                "last_updated": None,
            },
            "calendar": {"status": "pending", "items": [], "last_updated": None},
            "triage": {"status": "pending", "last_updated": None},
            "ticktick": {
                "status": "pending",
                "items": [],
                "later_count": 0,
                "open_count": 0,
                "more_count": 0,
                "last_updated": None,
            },
            "focus": {"status": "pending", "items": [], "last_updated": None},
            "pipeline": {"status": "pending", "last_updated": None},
            "vault_notes": {"status": "pending", "last_updated": None},
            "recent_meetings": {"status": "pending", "last_updated": None},
            "online_presence": {"status": "pending", "last_updated": None},
            "daily_brief": {"status": "pending", "last_updated": None},
            "slack_digest": {"status": "pending", "last_updated": None},
            "linear_digest": {"status": "pending", "last_updated": None},
        }
        self._lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue] = set()

    async def update(self, key: str, value: dict):
        async with self._lock:
            self.data[key] = value
            snapshot = json.dumps(self.data)
        await self._broadcast(snapshot)

    async def _broadcast(self, snapshot: str):
        for q in list(self._subscribers):
            await q.put(snapshot)

    async def snapshot_json(self) -> str:
        async with self._lock:
            return json.dumps(self.data)

    async def snapshot_dict(self) -> dict:
        async with self._lock:
            return dict(self.data)

    def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._subscribers.discard(q)


def _gmail_since_epoch(generated_at: str | None) -> int | None:
    """Unix seconds for Gmail `after:`, or None to use the 3-day fallback.

    A future `generated_at` (beyond small clock skew) is treated as a bad
    stamp — querying `after:` a time that hasn't happened yet always
    returns 0 and hides real unread mail.
    """
    gen = _parse_generated_at(generated_at)
    if gen is None:
        return None
    now = datetime.now(timezone.utc)
    if gen.tzinfo is None:
        gen = gen.replace(tzinfo=timezone.utc)
    if gen > now + timedelta(minutes=2):
        logger.warning(
            "triage generated_at is in the future (%s); using 3-day unread fallback",
            generated_at,
        )
        return None
    if gen > now:
        gen = now
    return int(gen.timestamp())


async def gmail_loop(state: AppState, creds_holder: CredentialsHolder):
    while True:
        try:
            triage = (await state.snapshot_dict()).get("triage") or {}
            if triage.get("status") == "pending":
                await asyncio.sleep(2)
                continue
            creds = await asyncio.to_thread(creds_holder.get)
            since_epoch = _gmail_since_epoch(triage.get("generated_at"))
            count, query, count_window = await asyncio.to_thread(
                fetch_gmail_unread_count, creds, since_epoch
            )
            await state.update(
                "gmail",
                {
                    "status": "ok",
                    "unread_count": count,
                    "count_window": count_window,
                    "query": query,
                    "last_updated": now_iso(),
                },
            )
            items = triage.get("items") or []
            if any((it.get("source") or "").lower() == "gmail" for it in items if isinstance(it, dict)):
                resolved = await asyncio.to_thread(resolve_triage_gmail_links, creds, items)
                if resolved != items:
                    await state.update("triage", {**triage, "items": resolved})
        except GoogleAuthError as e:
            logger.error("gmail auth error: %s", e)
            await state.update(
                "gmail",
                {"status": "unavailable", "error": str(e), "unread_count": None, "last_updated": now_iso()},
            )
        except Exception as e:
            logger.exception("gmail poll failed")
            await state.update(
                "gmail",
                {"status": "error", "error": str(e), "unread_count": None, "last_updated": now_iso()},
            )
        await asyncio.sleep(GMAIL_POLL_SECONDS)


async def calendar_loop(state: AppState, creds_holder: CredentialsHolder):
    while True:
        try:
            creds = await asyncio.to_thread(creds_holder.get)
            items = await asyncio.to_thread(fetch_calendar_events, creds)
            await state.update(
                "calendar", {"status": "ok", "items": items, "last_updated": now_iso()}
            )
        except GoogleAuthError as e:
            logger.error("calendar auth error: %s", e)
            await state.update(
                "calendar",
                {"status": "unavailable", "error": str(e), "items": [], "last_updated": now_iso()},
            )
        except Exception as e:
            logger.exception("calendar poll failed")
            await state.update(
                "calendar",
                {"status": "error", "error": str(e), "items": [], "last_updated": now_iso()},
            )
        await asyncio.sleep(CALENDAR_POLL_SECONDS)


def _parse_generated_at(generated_at: str | None) -> datetime | None:
    if not generated_at:
        return None
    try:
        v = generated_at[:-1] + "+00:00" if generated_at.endswith("Z") else generated_at
        return datetime.fromisoformat(v)
    except ValueError:
        return None


def _is_triage_stale(generated_at: str | None) -> bool:
    """Stale = a scheduled triage run (TRIAGE_RUN_TIMES, weekdays, local
    time) finished more than TRIAGE_GRACE ago without a newer snapshot.
    Judged against the schedule rather than a fixed age, so a quiet
    afternoon isn't flagged but a missed 06:45 run is.
    """
    gen = _parse_generated_at(generated_at)
    if gen is None:
        return False
    now_local = datetime.now(timezone.utc).astimezone(LOCAL_TZ)
    day = now_local
    for _ in range(7):
        if day.weekday() < 5:
            for hh, mm in reversed(TRIAGE_RUN_TIMES):
                slot = day.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if slot + TRIAGE_GRACE <= now_local:
                    return gen < slot
        day = (day - timedelta(days=1)).replace(hour=23, minute=59)
    return False


def _triage_item_link(item: dict) -> str | None:
    """Prefer Hermes's URL; for Gmail with no link, a Gmail-safe search hash.

    Percent-encoding the hash (e.g. `:` → `%3A`) makes Gmail's SPA render a
    blank page. Thread permalinks are filled in later by the Gmail poll.
    """
    raw = item.get("link")
    source = (item.get("source") or "").strip().lower()
    summary = (item.get("summary") or "").strip()
    if source == "gmail" and summary:
        thread = cached_gmail_thread_url(summary)
        if thread:
            return thread
        if isinstance(raw, str) and raw.strip() and "#search/" not in raw:
            return raw.strip()
        q = gmail_keyword_query(summary) or summary
        return gmail_ui_search_url(q)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _enrich_triage_items(items) -> list:
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        row = dict(it)
        row["link"] = _triage_item_link(row)
        out.append(row)
    return out


def _read_triage_snapshot() -> dict:
    path = os.path.join(TRIAGE_DATA_DIR, "triage_snapshot.json")
    if not os.path.isfile(path):
        return {"status": "empty", "last_updated": now_iso()}
    try:
        with open(path, encoding="utf-8") as f:
            snap = json.load(f)
        generated_at = snap.get("generated_at")
        return {
            "status": "ok",
            "generated_at": generated_at,
            "channel": snap.get("channel"),
            "unread_count": snap.get("unread_count"),
            "items": _enrich_triage_items(snap.get("items", [])),
            "stale": _is_triage_stale(generated_at),
            "last_updated": now_iso(),
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "last_updated": now_iso()}


async def triage_loop(state: AppState):
    while True:
        snap = await asyncio.to_thread(_read_triage_snapshot)
        await state.update("triage", snap)
        await asyncio.sleep(TRIAGE_POLL_SECONDS)


def _ticktick_error_payload(status: str, error: str) -> dict:
    return {
        "status": status,
        "error": error,
        "items": [],
        "later_count": 0,
        "open_count": 0,
        "more_count": 0,
        "last_updated": now_iso(),
    }


async def ticktick_loop(state: AppState):
    while True:
        try:
            payload = await asyncio.to_thread(ticktick_client.fetch_open_tasks)
            await state.update(
                "ticktick",
                {
                    "status": "ok",
                    "items": payload["items"],
                    "later_count": payload["later_count"],
                    "open_count": payload["open_count"],
                    "more_count": payload["more_count"],
                    "last_updated": now_iso(),
                },
            )
        except ticktick_client.TickTickAuthError as e:
            logger.error("ticktick auth error: %s", e)
            await state.update("ticktick", _ticktick_error_payload("unavailable", str(e)))
        except Exception as e:
            logger.exception("ticktick poll failed")
            await state.update("ticktick", _ticktick_error_payload("error", str(e)))
        await asyncio.sleep(TICKTICK_POLL_SECONDS)


async def focus_loop(state: AppState):
    while True:
        try:
            snap = await state.snapshot_dict()
            now = datetime.now(timezone.utc)
            items = focus_module.compute_focus(
                triage=snap.get("triage"),
                calendar=snap.get("calendar"),
                ticktick=snap.get("ticktick"),
                now=now,
                tz=LOCAL_TZ,
            )
            await state.update("focus", {"status": "ok", "items": items, "last_updated": now_iso()})
        except Exception as e:
            logger.exception("focus computation failed")
            await state.update(
                "focus", {"status": "error", "error": str(e), "items": [], "last_updated": now_iso()}
            )
        snap = await state.snapshot_dict()
        pending = any(
            (snap.get(k) or {}).get("status") == "pending" for k in ("triage", "calendar", "ticktick")
        )
        await asyncio.sleep(2 if pending else FOCUS_POLL_SECONDS)
