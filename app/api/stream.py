"""Server-sent events for the slow AI endpoints.

The Report and Predict calls take many seconds and the app shows a terminal-style
loader with a step list. Without progress events those steps are a guess; with
them, each one ticks when the server actually reaches that stage.

The work runs as a task while this drains a queue, so stages are delivered as
they happen rather than all at once at the end. Three event types are emitted:

    event: stage    data: {"stage": "news"}
    event: result   data: {...the same JSON the non-streaming endpoint returns}
    event: second   data: {"secondOpinion": {...}}   (Predict only)

`result` is always sent — including on failure, carrying the same error shape the
plain endpoint would have returned — so a client never has to guess why a stream
ended. The non-streaming endpoints stay exactly as they were, so the app can fall
back to them if streaming misbehaves on a device.

`second` exists because the two analysts finish at very different times (measured
live: OpenAI ~6s, DeepSeek ~20s). Waiting for both before sending anything means
staring at a loader for ~11s after the answer is ready, so the headline read goes
out first and the second opinion follows on the same connection.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable

logger = logging.getLogger("stockpulse.api.stream")

# Nothing should hold the connection open forever if a stage never arrives.
_HEARTBEAT_SECONDS = 15.0


def _event(name: str, payload: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def sse_events(
    run: Callable[[Callable[[str, dict], None]], Awaitable[dict]],
) -> AsyncIterator[str]:
    """Drive `run`, forwarding whatever events it emits, as it emits them.

    `run` is handed `emit(name, payload)` and may send any event at any point.
    If it never sends a `result`, its return value is sent as one — which is what
    keeps every early error path working without each one having to remember.
    """
    queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()

    def emit(name: str, payload: dict) -> None:
        queue.put_nowait((name, payload))

    task = asyncio.create_task(run(emit))
    sent_result = False

    try:
        while True:
            # Race the next event against the work finishing, so a fast run ends
            # immediately instead of waiting out the heartbeat.
            getter = asyncio.ensure_future(queue.get())
            done, _ = await asyncio.wait(
                {getter, task},
                return_when=asyncio.FIRST_COMPLETED,
                timeout=_HEARTBEAT_SECONDS,
            )
            if getter in done:
                name, payload = getter.result()
                sent_result = sent_result or name == "result"
                yield _event(name, payload)
                continue

            # Nothing was read; cancelling leaves any queued item in place, and
            # the drain below picks it up.
            getter.cancel()
            if task in done:
                break
            # A comment line keeps proxies from closing an idle connection.
            yield ": keep-alive\n\n"

        result = await task
    except asyncio.CancelledError:
        task.cancel()  # client hung up — don't leave the work running
        raise
    except Exception as exc:  # the pipeline blew up in a way it doesn't handle
        logger.warning("Streaming endpoint failed: %s", exc, exc_info=True)
        yield _event("result", {"ok": False, "reason": "Something went wrong."})
        return

    # Drain anything queued between the last read and the task finishing.
    while not queue.empty():
        name, payload = queue.get_nowait()
        sent_result = sent_result or name == "result"
        yield _event(name, payload)

    if not sent_result:
        yield _event("result", result)


async def sse_with_progress(
    run: Callable[[Callable[[str], None]], Awaitable[dict]],
) -> AsyncIterator[str]:
    """Stage events then a result — the original, narrower contract.

    Kept because most callers only ever report progress; they should not have to
    think about event names.
    """

    async def wrapped(emit):
        return await run(lambda stage: emit("stage", {"stage": stage}))

    async for chunk in sse_events(wrapped):
        yield chunk


SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    # Nginx buffers proxied responses by default, which would defeat the point.
    "X-Accel-Buffering": "no",
}
