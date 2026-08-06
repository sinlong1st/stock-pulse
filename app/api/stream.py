"""Server-sent events for the slow AI endpoints.

The Report and Predict calls take many seconds and the app shows a terminal-style
loader with a step list. Without progress events those steps are a guess; with
them, each one ticks when the server actually reaches that stage.

The work runs as a task while this drains a queue, so stages are delivered as
they happen rather than all at once at the end. Two event types are emitted:

    event: stage    data: {"stage": "news"}
    event: result   data: {...the same JSON the non-streaming endpoint returns}

`result` is always sent — including on failure, carrying the same error shape the
plain endpoint would have returned — so a client never has to guess why a stream
ended. The non-streaming endpoints stay exactly as they were, so the app can fall
back to them if streaming misbehaves on a device.
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


async def sse_with_progress(
    run: Callable[[Callable[[str], None]], Awaitable[dict]],
) -> AsyncIterator[str]:
    """Drive `run`, streaming its stage callbacks then its result.

    `run` is handed a `progress(stage)` function it can call from anywhere in
    the pipeline; calls are thread-safe in the sense that matters here (they only
    put onto an asyncio queue from the same loop).
    """
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def progress(stage: str) -> None:
        queue.put_nowait(stage)

    task = asyncio.create_task(run(progress))

    try:
        while True:
            # Race the next stage against the work finishing, so a fast run ends
            # immediately instead of waiting out the heartbeat.
            getter = asyncio.ensure_future(queue.get())
            done, _ = await asyncio.wait(
                {getter, task},
                return_when=asyncio.FIRST_COMPLETED,
                timeout=_HEARTBEAT_SECONDS,
            )
            if getter in done:
                stage = getter.result()
                if stage is None:
                    break
                yield _event("stage", {"stage": stage})
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

    # Drain any stages queued between the last read and the task finishing.
    while not queue.empty():
        stage = queue.get_nowait()
        if stage is not None:
            yield _event("stage", {"stage": stage})

    yield _event("result", result)


SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    # Nginx buffers proxied responses by default, which would defeat the point.
    "X-Accel-Buffering": "no",
}
