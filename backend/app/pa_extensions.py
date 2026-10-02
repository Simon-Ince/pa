"""Reads the extra PA Command Center feed files written by Hermes cron
scripts (pipeline_status.json, vault_notes.json, recent_meetings.json,
online_presence.json) from the same read-only TRIAGE_DATA_DIR mount used
for triage_snapshot.json. No new mounts needed — all four live alongside
the existing triage snapshot in dashboard_data/.
"""
import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("pa.extensions")

TRIAGE_DATA_DIR = os.environ.get("TRIAGE_DATA_DIR", "/data")

EXTRA_POLL_SECONDS = 60


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(filename: str) -> dict:
    path = os.path.join(TRIAGE_DATA_DIR, filename)
    if not os.path.isfile(path):
        return {"status": "empty", "last_updated": now_iso()}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        data["last_updated"] = now_iso()
        return data
    except Exception as e:
        return {"status": "error", "error": str(e), "last_updated": now_iso()}


def read_pipeline_status() -> dict:
    return _read_json("pipeline_status.json")


def read_vault_notes() -> dict:
    return _read_json("vault_notes.json")


def read_recent_meetings() -> dict:
    return _read_json("recent_meetings.json")


def read_online_presence() -> dict:
    return _read_json("online_presence.json")


def read_daily_brief() -> dict:
    return _read_json("daily_brief.json")


async def pipeline_loop(state, asyncio_module, sleep_seconds=EXTRA_POLL_SECONDS):
    while True:
        try:
            data = await asyncio_module.to_thread(read_pipeline_status)
            await state.update("pipeline", data)
        except Exception as e:
            logger.exception("pipeline status poll failed")
            await state.update("pipeline", {"status": "error", "error": str(e), "last_updated": now_iso()})
        await asyncio_module.sleep(sleep_seconds)


async def vault_notes_loop(state, asyncio_module, sleep_seconds=EXTRA_POLL_SECONDS):
    while True:
        try:
            data = await asyncio_module.to_thread(read_vault_notes)
            await state.update("vault_notes", data)
        except Exception as e:
            logger.exception("vault notes poll failed")
            await state.update("vault_notes", {"status": "error", "error": str(e), "last_updated": now_iso()})
        await asyncio_module.sleep(sleep_seconds)


async def recent_meetings_loop(state, asyncio_module, sleep_seconds=EXTRA_POLL_SECONDS):
    while True:
        try:
            data = await asyncio_module.to_thread(read_recent_meetings)
            await state.update("recent_meetings", data)
        except Exception as e:
            logger.exception("recent meetings poll failed")
            await state.update("recent_meetings", {"status": "error", "error": str(e), "last_updated": now_iso()})
        await asyncio_module.sleep(sleep_seconds)


async def online_presence_loop(state, asyncio_module, sleep_seconds=EXTRA_POLL_SECONDS):
    while True:
        try:
            data = await asyncio_module.to_thread(read_online_presence)
            await state.update("online_presence", data)
        except Exception as e:
            logger.exception("online presence poll failed")
            await state.update("online_presence", {"status": "error", "error": str(e), "last_updated": now_iso()})
        await asyncio_module.sleep(sleep_seconds)


async def daily_brief_loop(state, asyncio_module, sleep_seconds=EXTRA_POLL_SECONDS):
    while True:
        try:
            data = await asyncio_module.to_thread(read_daily_brief)
            await state.update("daily_brief", data)
        except Exception as e:
            logger.exception("daily brief poll failed")
            await state.update("daily_brief", {"status": "error", "error": str(e), "last_updated": now_iso()})
        await asyncio_module.sleep(sleep_seconds)
