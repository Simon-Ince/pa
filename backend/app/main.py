import asyncio
import json
import logging
import mimetypes
import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
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
    _background_tasks.append(asyncio.create_task(pa_extensions.slack_digest_loop(state, asyncio)))
    _background_tasks.append(asyncio.create_task(pa_extensions.linear_digest_loop(state, asyncio)))
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
_BYTES_RANGE = re.compile(r"bytes=(\d*)-(\d*)$")


def _read_span(path: str, start: int, length: int) -> bytes:
    with open(path, "rb") as handle:
        handle.seek(start)
        return handle.read(length)


def _audio_not_found(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": message},
        headers={"Cache-Control": "no-store"},
    )


async def _serve_brief_audio(request: Request, filename: str | None = None):
    """Serves the brief audio by basename in the read-only /audio mount.

    The host path stored in daily_brief.json does not exist inside the
    container. Browsers (Safari especially) will not start playback unless
    the response answers Range requests with 206 and a filename they can
    treat as media.
    """
    snap = (await state.snapshot_dict()).get("daily_brief") or {}
    audio_path = snap.get("audio_path")
    if not audio_path:
        return _audio_not_found("no audio available")
    expected = os.path.basename(str(audio_path))
    if filename is not None and filename != expected:
        return _audio_not_found("audio file not found")
    local_path = os.path.join(AUDIO_CACHE_DIR, expected)
    if not os.path.isfile(local_path):
        return _audio_not_found("audio file not found")

    size = os.path.getsize(local_path)
    media_type = mimetypes.guess_type(expected)[0] or "audio/mpeg"
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-cache",
    }
    if request.method == "HEAD":
        return Response(
            status_code=200,
            media_type=media_type,
            headers={**headers, "Content-Length": str(size)},
        )

    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(local_path, media_type=media_type, headers=headers)

    # A multipart range is not needed for a single audio element.
    match = _BYTES_RANGE.match(range_header.split(",", 1)[0].strip())
    if not match or (match.group(1) == "" and match.group(2) == ""):
        return Response(
            status_code=416,
            headers={**headers, "Content-Range": f"bytes */{size}"},
        )
    start_s, end_s = match.group(1), match.group(2)
    if start_s == "":
        suffix = int(end_s)
        if suffix <= 0:
            return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"})
        start = max(size - suffix, 0)
        end = size - 1
    else:
        start = int(start_s)
        end = int(end_s) if end_s else size - 1
    if start < 0 or start >= size or end < start:
        return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"})
    end = min(end, size - 1)
    length = end - start + 1
    data = await asyncio.to_thread(_read_span, local_path, start, length)
    return Response(
        content=data,
        status_code=206,
        headers={
            **headers,
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(length),
        },
        media_type=media_type,
    )


@app.api_route("/api/daily-brief/audio", methods=["GET", "HEAD"])
async def daily_brief_audio(request: Request):
    return await _serve_brief_audio(request)


@app.api_route("/api/daily-brief/audio/{filename}", methods=["GET", "HEAD"])
async def daily_brief_audio_file(filename: str, request: Request):
    return await _serve_brief_audio(request, filename)
