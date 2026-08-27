"""Aggregates the four data sources into one small JSON state object, polls
them in the background, and fans out updates to SSE subscribers.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import focus as focus_module
from . import ticktick_client
from .google_client import (
    CredentialsHolder,
    GoogleAuthError,
    fetch_calendar_events,
    fetch_gmail_unread_count,
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
TRIAGE_STALE_HOURS = 7
WORK_HOURS_START = 8
WORK_HOURS_END = 18


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
            "ticktick": {"status": "pending", "items": [], "last_updated": None},
            "focus": {"status": "pending", "items": [], "last_updated": None},
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


async def gmail_loop(state: AppState, creds_holder: CredentialsHolder):
    while True:
        try:
            creds = await asyncio.to_thread(creds_holder.get)
            triage = (await state.snapshot_dict()).get("triage") or {}
            gen = _parse_generated_at(triage.get("generated_at"))
            since_epoch = int(gen.timestamp()) if gen is not None else None
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
    """Stale = the snapshot is older than TRIAGE_STALE_HOURS *and* it's
    currently within weekday work hours (no point flagging staleness at
    2am — nothing's happened since the last run anyway).
    """
    gen = _parse_generated_at(generated_at)
    if gen is None:
        return False
    now = datetime.now(timezone.utc)
    age_hours = (now - gen).total_seconds() / 3600
    if age_hours < TRIAGE_STALE_HOURS:
        return False
    local_now = now.astimezone(LOCAL_TZ)
    if local_now.weekday() >= 5:
        return False
    return WORK_HOURS_START <= local_now.hour < WORK_HOURS_END


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
            "items": snap.get("items", []),
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


async def ticktick_loop(state: AppState):
    while True:
        try:
            items = await asyncio.to_thread(ticktick_client.fetch_open_tasks)
            await state.update(
                "ticktick", {"status": "ok", "items": items, "last_updated": now_iso()}
            )
        except ticktick_client.TickTickAuthError as e:
            logger.error("ticktick auth error: %s", e)
            await state.update(
                "ticktick",
                {"status": "unavailable", "error": str(e), "items": [], "last_updated": now_iso()},
            )
        except Exception as e:
            logger.exception("ticktick poll failed")
            await state.update(
                "ticktick",
                {"status": "error", "error": str(e), "items": [], "last_updated": now_iso()},
            )
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
        await asyncio.sleep(FOCUS_POLL_SECONDS)
