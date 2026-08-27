"""Aggregates the four data sources into one small JSON state object, polls
them in the background, and fans out updates to SSE subscribers.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone

from . import weekly_notes
from .google_client import CredentialsHolder, GoogleAuthError, fetch_calendar_events, fetch_gmail_unread

logger = logging.getLogger("pa.state")

GMAIL_POLL_SECONDS = 50
CALENDAR_POLL_SECONDS = 60
WEEKLY_NOTES_POLL_SECONDS = 120
TRIAGE_POLL_SECONDS = 90
HEARTBEAT_SECONDS = 25

VAULT_DIR = os.environ.get("VAULT_WEEKLY_NOTES_DIR", "/vault/Weekly Notes")
TRIAGE_DATA_DIR = os.environ.get("TRIAGE_DATA_DIR", "/data")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_section(status: str) -> dict:
    return {"status": status, "last_updated": None}


class AppState:
    def __init__(self):
        self.data = {
            "gmail": {"status": "pending", "items": [], "last_updated": None},
            "calendar": {"status": "pending", "items": [], "last_updated": None},
            "weekly_notes": {
                "status": "pending",
                "note_file": None,
                "week_start": None,
                "days": {d: [] for d in weekly_notes.DAY_NAMES},
                "last_updated": None,
            },
            "triage": {"status": "pending", "last_updated": None},
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
            items = await asyncio.to_thread(fetch_gmail_unread, creds)
            await state.update(
                "gmail", {"status": "ok", "items": items, "last_updated": now_iso()}
            )
        except GoogleAuthError as e:
            logger.error("gmail auth error: %s", e)
            await state.update(
                "gmail",
                {"status": "unavailable", "error": str(e), "items": [], "last_updated": now_iso()},
            )
        except Exception as e:
            logger.exception("gmail poll failed")
            await state.update(
                "gmail",
                {"status": "error", "error": str(e), "items": [], "last_updated": now_iso()},
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


async def weekly_notes_loop(state: AppState):
    while True:
        try:
            path, monday = await asyncio.to_thread(weekly_notes.find_current_week_note, VAULT_DIR)
            if path:
                days = await asyncio.to_thread(weekly_notes.parse_open_items, path)
                await state.update(
                    "weekly_notes",
                    {
                        "status": "ok",
                        "note_file": os.path.basename(path),
                        "week_start": monday.isoformat(),
                        "days": days,
                        "last_updated": now_iso(),
                    },
                )
            else:
                await state.update(
                    "weekly_notes",
                    {
                        "status": "not_found",
                        "note_file": None,
                        "week_start": monday.isoformat(),
                        "days": {d: [] for d in weekly_notes.DAY_NAMES},
                        "last_updated": now_iso(),
                    },
                )
        except Exception as e:
            logger.exception("weekly notes parse failed")
            await state.update(
                "weekly_notes",
                {"status": "error", "error": str(e), "days": {d: [] for d in weekly_notes.DAY_NAMES}, "last_updated": now_iso()},
            )
        await asyncio.sleep(WEEKLY_NOTES_POLL_SECONDS)


def _read_triage_snapshot() -> dict:
    path = os.path.join(TRIAGE_DATA_DIR, "triage_snapshot.json")
    if not os.path.isfile(path):
        return {"status": "empty", "last_updated": now_iso()}
    try:
        with open(path, encoding="utf-8") as f:
            snap = json.load(f)
        return {
            "status": "ok",
            "generated_at": snap.get("generated_at"),
            "channel": snap.get("channel"),
            "items": snap.get("items", []),
            "last_updated": now_iso(),
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "last_updated": now_iso()}


async def triage_loop(state: AppState):
    while True:
        snap = await asyncio.to_thread(_read_triage_snapshot)
        await state.update("triage", snap)
        await asyncio.sleep(TRIAGE_POLL_SECONDS)
