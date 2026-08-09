/**
 * Minimal server-sent-events reader for React Native.
 *
 * RN's `fetch` does not expose a streaming `response.body`, and there is no
 * `EventSource`, so this uses XMLHttpRequest — which *does* surface partial
 * `responseText` as bytes arrive. We track how much we've already parsed and
 * only handle the new tail.
 *
 * Deliberately tiny: it understands the three event types this app sends
 * (`stage`, `result` and `second`) and nothing else. Any failure is reported
 * through `onError` so callers can fall back to the plain JSON endpoint.
 */
import { API_BASE_URL, API_TOKEN } from '../config';

export type SseHandlers<T, L = unknown> = {
  onStage?: (stage: string) => void;
  onResult: (result: T) => void;
  /** A `second` event, which arrives *after* `onResult`. Predict streams the
   *  slower model's opinion this way so the main read isn't held up by it. */
  onLate?: (payload: L) => void;
  onError: (error: Error) => void;
};

export type SseHandle = { cancel: () => void };

/** Parse whole SSE blocks out of `text`, returning them and the leftover tail. */
function splitBlocks(text: string): { blocks: string[]; rest: string } {
  const parts = text.split('\n\n');
  // The final piece may be a partial block still being received.
  const rest = parts.pop() ?? '';
  return { blocks: parts, rest };
}

export function streamSse<T, L = unknown>(
  path: string,
  handlers: SseHandlers<T, L>,
): SseHandle {
  const xhr = new XMLHttpRequest();
  let consumed = 0; // characters of responseText already parsed
  let buffer = '';
  let settled = false; // a result has been delivered
  // Separate from `settled` on purpose: `second` legitimately arrives after the
  // result, so it can't key off that — but it must still stop on cancel.
  let cancelled = false;

  const fail = (message: string) => {
    if (settled) return;
    settled = true;
    handlers.onError(new Error(message));
  };

  const handleBlock = (block: string) => {
    let event = 'message';
    const data: string[] = [];
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) data.push(line.slice(5).trim());
      // ':' comment lines (keep-alives) are ignored.
    }
    if (!data.length) return;
    let parsed: unknown;
    try {
      parsed = JSON.parse(data.join('\n'));
    } catch {
      return; // a malformed block is not worth failing the whole stream over
    }
    if (event === 'stage') {
      const stage = (parsed as { stage?: string })?.stage;
      if (stage) handlers.onStage?.(stage);
    } else if (event === 'result') {
      if (settled) return;
      settled = true;
      handlers.onResult(parsed as T);
    } else if (event === 'second') {
      if (cancelled) return;
      handlers.onLate?.(parsed as L);
    }
  };

  const drain = () => {
    const text = xhr.responseText ?? '';
    if (text.length <= consumed) return;
    buffer += text.slice(consumed);
    consumed = text.length;
    const { blocks, rest } = splitBlocks(buffer);
    buffer = rest;
    blocks.forEach(handleBlock);
  };

  xhr.onreadystatechange = () => {
    // LOADING (3) fires repeatedly as chunks arrive; DONE (4) once at the end.
    if (xhr.readyState < 3) return;
    if (xhr.readyState === 4 && xhr.status !== 200) {
      fail(
        xhr.status === 401
          ? '401 Unauthorized — API token doesn’t match the server.'
          : `Server returned ${xhr.status}`,
      );
      return;
    }
    drain();
    if (xhr.readyState === 4 && !settled) {
      // Stream closed without a result event — treat as a failure so the
      // caller can retry over the plain endpoint.
      fail('The stream ended before a result arrived.');
    }
  };

  xhr.onerror = () => fail(`Can't reach ${API_BASE_URL} — is the server up?`);
  xhr.ontimeout = () => fail('The request timed out.');

  try {
    xhr.open('GET', `${API_BASE_URL.replace(/\/+$/, '')}${path}`);
    xhr.setRequestHeader('Authorization', `Bearer ${API_TOKEN}`);
    xhr.setRequestHeader('Accept', 'text/event-stream');
    xhr.send();
  } catch (e) {
    fail(e instanceof Error ? e.message : 'Could not start the request.');
  }

  return {
    cancel: () => {
      settled = true; // suppress the abort-triggered error
      cancelled = true; // and drop a second opinion still in flight
      xhr.abort();
    },
  };
}
