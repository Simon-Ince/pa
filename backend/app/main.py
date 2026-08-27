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
    logger.info("started %d background polling loops", len(_background_tasks))
    yield
    for t in _background_tasks:
        t.cancel()
    await asyncio.gather(*_background_tasks, return_exceptions=True)


app = FastAPI(title="PA Command Center", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


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
