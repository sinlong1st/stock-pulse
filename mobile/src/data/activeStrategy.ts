/**
 * Cross-screen signal for "the active strategy changed".
 *
 * A prediction already on screen was produced by whichever strategy was active
 * at the time, and it keeps rendering that strategy's name in the modal. Without
 * this, switching strategies in Settings looks like it did nothing — the Predict
 * tab still shows the old lens until you happen to run another prediction.
 *
 * Same tiny pub/sub shape as the watchlist cache; no dependency between screens.
 */
type Listener = (activeId: string) => void;

const listeners = new Set<Listener>();
let current: string | null = null;

/** Called after the server confirms a switch. No-ops if nothing changed. */
export function notifyActiveStrategy(activeId: string) {
  if (activeId === current) return;
  current = activeId;
  listeners.forEach((fn) => fn(activeId));
}

/** Record the active id without waking anyone — used on first load. */
export function primeActiveStrategy(activeId: string) {
  current = activeId;
}

export function onActiveStrategyChange(fn: Listener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}
