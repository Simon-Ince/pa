import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .google_client import CredentialsHolder
from .sse import event_stream
from .state import (
    AppState,
    calendar_loop,
    focus_loop,
    gmail_loop,
    ticktick_loop,
    triage_loop,
)
from . import pa_extensions

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("pa.main")

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

state = AppState()
creds_holder = CredentialsHolder()
_background_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    _background_tasks.append(asyncio.create_task(gmail_loop(state, creds_holder)))
    _background_tasks.append(asyncio.create_task(calendar_loop(state, creds_holder)))
    _background_tasks.append(asyncio.create_task(triage_loop(state)))
    _background_tasks.append(asyncio.create_task(ticktick_loop(state)))
    _background_tasks.append(asyncio.create_task(focus_loop(state)))
    _background_tasks.append(asyncio.create_task(pa_extensions.pipeline_loop(state, asyncio)))
    _background_tasks.append(asyncio.create_task(pa_extensions.vault_notes_loop(state, asyncio)))
    _background_tasks.append(asyncio.create_task(pa_extensions.recent_meetings_loop(state, asyncio)))
    _background_tasks.append(asyncio.create_task(pa_extensions.online_presence_loop(state, asyncio)))
    _background_tasks.append(asyncio.create_task(pa_extensions.daily_brief_loop(state, asyncio)))
    logger.info("started %d background polling loops", len(_background_tasks))
    yield
    for t in _background_tasks:
        t.cancel()
    await asyncio.gather(*_background_tasks, return_exceptions=True)


class NoCacheStaticFiles(StaticFiles):
    """Local always-on dashboard — never let the browser keep a stale CSS/JS."""

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


app = FastAPI(title="PA Command Center", lifespan=lifespan)
app.mount("/static", NoCacheStaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(
        os.path.join(STATIC_DIR, "index.html"),
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/api/state")
async def api_state():
    snapshot = await state.snapshot_json()
    return JSONResponse(content=json.loads(snapshot))


@app.get("/api/stream")
async def api_stream(request: Request):
    return StreamingResponse(
        event_stream(state),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


AUDIO_CACHE_DIR = os.environ.get("AUDIO_CACHE_DIR", "/audio")


@app.get("/api/daily-brief/audio")
async def daily_brief_audio():
    """Serves the mp3 the daily-brief cron generated, by basename lookup in
    the read-only /audio mount (host path in daily_brief.json won't exist
    inside the container, only its filename does)."""
    snap = (await state.snapshot_dict()).get("daily_brief") or {}
    audio_path = snap.get("audio_path")
    if not audio_path:
        return JSONResponse(status_code=404, content={"error": "no audio available"})
    filename = os.path.basename(audio_path)
    local_path = os.path.join(AUDIO_CACHE_DIR, filename)
    if not os.path.isfile(local_path):
        return JSONResponse(status_code=404, content={"error": "audio file not found"})
    return FileResponse(local_path, media_type="audio/mpeg")
