"""Server-sent events stream: pushes the aggregated state to browsers
whenever the backend's polling loops detect new data, plus a heartbeat.
"""
import asyncio
import logging

from .state import HEARTBEAT_SECONDS, AppState

logger = logging.getLogger("pa.sse")


def format_sse(data: str, event: str | None = None) -> str:
    lines = data.splitlines() or [""]
    payload = "\n".join(f"data: {line}" for line in lines)
    if event:
        return f"event: {event}\n{payload}\n\n"
    return f"{payload}\n\n"


async def event_stream(state: AppState):
    queue = state.subscribe()
    try:
        initial = await state.snapshot_json()
        yield format_sse(initial, event="state")
        while True:
            try:
                snapshot = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                yield format_sse(snapshot, event="state")
            except asyncio.TimeoutError:
                yield format_sse("{}", event="heartbeat")
    except asyncio.CancelledError:
        raise
    finally:
        state.unsubscribe(queue)
