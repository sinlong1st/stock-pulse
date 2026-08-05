/**
 * Shared watchlist access. `/api/watchlist` prices every ticker, so it's too
 * expensive to fetch once per component — the rows are cached module-wide and
 * handed to every caller, and mutations invalidate it.
 *
 * `guessTicker` is the client-side half of the backend's `resolve_focus`: it
 * maps what the user typed onto a watchlist ticker, typos included, so a loading
 * screen can name the stock before the server has confirmed it.
 */
import { useEffect, useState } from 'react';

import { fetchWatchlist } from './api';
import { WatchRow } from './types';

let cache: WatchRow[] | null = null;
let inflight: Promise<WatchRow[]> | null = null;
const listeners = new Set<(rows: WatchRow[]) => void>();

/**
 * Replace the cached rows and push them to every mounted consumer. The Watchlist
 * screen calls this after add/remove, so the pickers on other tabs — which stay
 * mounted in the tab navigator and would never refetch — stay in sync.
 */
export function primeWatchlist(rows: WatchRow[]) {
  cache = rows;
  listeners.forEach((fn) => fn(rows));
}

export function useWatchlist(): WatchRow[] {
  const [rows, setRows] = useState<WatchRow[]>(cache ?? []);

  useEffect(() => {
    listeners.add(setRows);
    return () => {
      listeners.delete(setRows);
    };
  }, []);

  useEffect(() => {
    if (cache) {
      setRows(cache);
      return;
    }
    let alive = true;
    const p = inflight ?? (inflight = fetchWatchlist());
    p.then((r) => {
      cache = r;
      inflight = null;
      if (alive) setRows(r);
    }).catch(() => {
      inflight = null; // let a later mount retry
    });
    return () => {
      alive = false;
    };
  }, []);

  return rows;
}

const norm = (s: string) => s.trim().toLowerCase().replace(/[^a-z0-9]/g, '');

/** Levenshtein, capped — we only care about "close enough to be a typo". */
function distance(a: string, b: string): number {
  if (Math.abs(a.length - b.length) > 3) return 99;
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const row = [i];
    for (let j = 1; j <= b.length; j++) {
      row[j] = Math.min(
        prev[j] + 1,
        row[j - 1] + 1,
        prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1),
      );
    }
    prev = row;
  }
  return prev[b.length];
}

/**
 * Best watchlist ticker for free text, or null when nothing is close enough.
 * Deliberately conservative — naming the wrong stock is worse than naming none.
 */
export function guessTicker(rows: WatchRow[], query: string): string | null {
  const q = norm(query);
  if (!q || !rows.length) return null;

  for (const r of rows) {
    if (norm(r.ticker) === q || norm(r.name) === q) return r.ticker;
  }
  if (q.length >= 3) {
    for (const r of rows) {
      if (norm(r.name).startsWith(q)) return r.ticker;
    }
  }

  let best: string | null = null;
  let bestD = Infinity;
  for (const r of rows) {
    for (const candidate of [norm(r.ticker), norm(r.name)]) {
      if (!candidate) continue;
      const d = distance(q, candidate);
      // Allow roughly one typo per three characters.
      if (d <= Math.max(1, Math.floor(candidate.length / 3)) && d < bestD) {
        bestD = d;
        best = r.ticker;
      }
    }
  }
  return best;
}
