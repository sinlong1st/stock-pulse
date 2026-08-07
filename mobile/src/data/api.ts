/**
 * Feed data source. Uses the real backend when `API_BASE_URL` is set in
 * config.ts; otherwise returns bundled mock data so the app always renders.
 */
import { API_BASE_URL, API_TOKEN } from '../config';
import { mockAlerts, mockEvaluation, mockPrediction, mockReport, mockWatchlist } from './mock';
import { streamSse } from './sse';
import { Alert, EarningsRow, Report, Sentiment, WatchRow } from './types';

/** True when no backend is configured (the app is showing sample data). */
export const usingMockData = !API_BASE_URL;

const base = () => API_BASE_URL.replace(/\/+$/, '');

function requireBackend() {
  if (!API_BASE_URL) throw new Error('No backend configured (running on sample data).');
}

/** Thrown when the caller aborted the request — callers should stay silent. */
export class AbortedError extends Error {
  constructor() {
    super('aborted');
    this.name = 'AbortedError';
  }
}

export const isAborted = (e: unknown) => e instanceof AbortedError;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${base()}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        'Content-Type': 'application/json',
        ...(init?.headers ?? {}),
      },
    });
  } catch (e) {
    // A cancel is not a failure — don't dress it up as an unreachable server.
    if (init?.signal?.aborted || (e as Error)?.name === 'AbortError') throw new AbortedError();
    throw new Error(`Can't reach ${base()} — is Tailscale ON and the URL right?`);
  }
  if (res.status === 401) {
    throw new Error('401 Unauthorized — API token doesn’t match the server.');
  }
  if (!res.ok) {
    throw new Error(`Server returned ${res.status} at ${path}`);
  }
  return (await res.json()) as T;
}

const getJson = <T>(path: string, signal?: AbortSignal) => request<T>(path, { signal });

export async function fetchFeed(limit = 30): Promise<Alert[]> {
  if (!API_BASE_URL) return mockAlerts;
  const data = await getJson<{ alerts?: Alert[] }>(`/api/feed?limit=${limit}`);
  return data.alerts ?? [];
}

export async function fetchWatchlist(): Promise<WatchRow[]> {
  if (!API_BASE_URL) return mockWatchlist;
  const data = await getJson<{ watchlist?: WatchRow[] }>('/api/watchlist');
  return data.watchlist ?? [];
}

/** Generate a briefing on the server (one OpenAI call) — trigger on demand.
 * Pass a query (ticker or company name) for a focused single-stock report. */
export async function fetchReport(query?: string, signal?: AbortSignal): Promise<Report> {
  if (!API_BASE_URL) return mockReport;
  const q = query?.trim() ? `?q=${encodeURIComponent(query.trim())}` : '';
  return getJson<Report>(`/api/report${q}`, signal);
}

// --- settings + watchlist mutations ---------------------------------------

export type Language = { code: string; name: string };
export type Channels = {
  telegram: { enabled: boolean; configured: boolean };
  push: { enabled: boolean };
};
export type BriefingInfo = {
  enabled: boolean;
  timezone: string;
  morningAt: string;
  intradayEveryHours: number;
  intradayUntil: string;
  wrapAt: string;
  editable: boolean;
};
export type SettingsInfo = {
  language: string;
  languageCode: string | null;
  languages: Language[];
  channels: Channels;
  briefing: BriefingInfo;
};

export async function fetchSettings(): Promise<SettingsInfo> {
  requireBackend();
  return getJson<SettingsInfo>('/api/settings');
}

export async function setLanguage(code: string): Promise<{ language: string }> {
  requireBackend();
  return request<{ language: string }>('/api/settings/language', {
    method: 'POST',
    body: JSON.stringify({ code }),
  });
}

export async function setChannel(channel: 'telegram' | 'push', enabled: boolean): Promise<void> {
  requireBackend();
  await request('/api/settings/channels', {
    method: 'POST',
    body: JSON.stringify({ channel, enabled }),
  });
}

export type AddResult = { added: boolean; ticker?: string; name?: string; reason?: string | null };

export async function addWatch(query: string): Promise<AddResult> {
  requireBackend();
  return request<AddResult>('/api/watchlist', {
    method: 'POST',
    body: JSON.stringify({ query }),
  });
}

export async function removeWatch(ticker: string): Promise<{ removed: boolean }> {
  requireBackend();
  return request<{ removed: boolean }>(`/api/watchlist/${encodeURIComponent(ticker)}`, {
    method: 'DELETE',
  });
}

export type EvalStat = {
  accuracyPct: number | null;
  hits: number;
  misses: number;
  total: number;
  avgReturnPct: number | null;
};
/** How one strategy's Predict calls have turned out. `enoughData` is false
 *  while the sample is too thin for the percentage to mean anything. */
export type StrategyStat = {
  id: string;
  name: string;
  builtin: boolean;
  total: number;
  hits: number;
  misses: number;
  flats: number;
  accuracyPct: number | null;
  avgReturnPct: number | null;
  pending: number;
  enoughData: boolean;
};

export type EvalReport = {
  totalEvaluated: number;
  accuracyPct: number | null;
  pending: number;
  bullish: EvalStat;
  bearish: EvalStat;
  strategies?: StrategyStat[]; // absent on older backends
  minMeaningfulCalls?: number;
  recent: {
    ticker: string;
    sentiment: Sentiment;
    horizon: string;
    returnPct: number | null;
    outcome: string;
  }[];
};

export async function fetchEvaluation(): Promise<EvalReport> {
  if (!API_BASE_URL) return mockEvaluation;
  return getJson<EvalReport>('/api/evaluation');
}

export type Lean = 'bounce' | 'dip' | 'hold';
export type PredictionHorizon = {
  horizon: string;
  lean: Lean;
  confidence: 'low' | 'medium' | 'high';
  rationale: string;
};
export type Prediction = {
  ok: boolean;
  reason?: string;
  ticker?: string;
  name?: string;
  price?: string | null;
  priceFresh?: string | null;
  discount?: { level: 'cheap' | 'fair' | 'rich'; vsRangeNote: string; note: string };
  trend?: 'up' | 'down' | 'sideways';
  enoughHistory?: boolean;
  horizons?: PredictionHorizon[];
  drivers?: string[];
  entry?: { assessment: 'good' | 'fair' | 'wait'; note: string };
  // near/long are the closest level of each (kept for older payloads);
  // nearLevels/longLevels carry up to three, closest first.
  support?: {
    near: number | null;
    long: number | null;
    nearLevels?: number[];
    longLevels?: number[];
  };
  earnings?: EarningsRow | null;
  strategy?: { id: string; name: string; body: string };
  series?: { closes: number[]; volumes: number[]; dates?: string[] };
  language?: string;
  disclaimer?: string;
};

export async function fetchPrediction(query: string, signal?: AbortSignal): Promise<Prediction> {
  if (!API_BASE_URL) return mockPrediction;
  return getJson<Prediction>(`/api/predict?q=${encodeURIComponent(query.trim())}`, signal);
}

// --- streaming variants ----------------------------------------------------
//
// The plain endpoints above still exist and still work; these add real progress
// events. Every caller falls back to the plain one if streaming fails, so a
// proxy that buffers SSE (or an old backend) degrades to today's behaviour
// rather than breaking.

export type StreamHandle = { cancel: () => void };

/**
 * Stage keys the backend emits, in order — these must match REPORT_STAGES in
 * app/api/report.py and PREDICT_STAGES in app/prediction/service.py. The loader
 * renders one step per entry, so the labels are indexed off these.
 */
export const REPORT_STAGES = ['news', 'prices', 'analyze', 'compose'];
export const PREDICT_STAGES = ['resolve', 'prices', 'news', 'analyze'];

function streamOrFallback<T>(
  path: string,
  fallback: (signal: AbortSignal) => Promise<T>,
  onStage: (stage: string) => void,
  onDone: (result: T) => void,
  onError: (error: Error) => void,
): StreamHandle {
  let cancelled = false;
  // Cancelling must also stop a fallback request that's already in flight.
  const ctrl = new AbortController();
  const handle = streamSse<T>(path, {
    onStage,
    onResult: (result) => !cancelled && onDone(result),
    onError: () => {
      if (cancelled) return;
      // Streaming didn't work — take the ordinary path so the user still gets
      // their answer, just without live stages.
      fallback(ctrl.signal)
        .then((r) => !cancelled && onDone(r))
        .catch((e) => {
          if (cancelled || isAborted(e)) return;
          onError(e instanceof Error ? e : new Error(String(e)));
        });
    },
  });
  return {
    cancel: () => {
      cancelled = true;
      handle.cancel();
      ctrl.abort();
    },
  };
}

/** Generate a briefing, reporting real pipeline stages as they happen. */
export function streamReport(
  query: string | undefined,
  onStage: (stage: string) => void,
  onDone: (report: Report) => void,
  onError: (error: Error) => void,
): StreamHandle {
  if (!API_BASE_URL) {
    onDone(mockReport);
    return { cancel: () => {} };
  }
  const q = query?.trim() ? `?q=${encodeURIComponent(query.trim())}` : '';
  return streamOrFallback(
    `/api/report/stream${q}`,
    (signal) => fetchReport(query, signal),
    onStage,
    onDone,
    onError,
  );
}

/** Forward-looking read, reporting real pipeline stages as they happen. */
export function streamPrediction(
  query: string,
  onStage: (stage: string) => void,
  onDone: (prediction: Prediction) => void,
  onError: (error: Error) => void,
): StreamHandle {
  if (!API_BASE_URL) {
    onDone(mockPrediction);
    return { cancel: () => {} };
  }
  const q = `?q=${encodeURIComponent(query.trim())}`;
  return streamOrFallback(
    `/api/predict/stream${q}`,
    (signal) => fetchPrediction(query, signal),
    onStage,
    onDone,
    onError,
  );
}

// --- prediction strategies -------------------------------------------------

export type StrategyItem = {
  id: string;
  name: string;
  body: string;
  builtin: boolean;
  active: boolean;
};
export type StrategiesInfo = {
  strategies: StrategyItem[];
  activeId: string;
  limits: { nameChars: number; bodyChars: number; minBodyChars: number };
};

/** Save the briefing schedule. The server validates and reinstalls its cron
 *  jobs immediately, so a change takes effect without a restart. */
export async function saveBriefingSchedule(schedule: {
  enabled: boolean;
  morningAt: string;
  intradayEveryHours: number;
  intradayUntil: string;
  wrapAt: string;
}): Promise<BriefingInfo> {
  requireBackend();
  return request<BriefingInfo>('/api/briefing', {
    method: 'POST',
    body: JSON.stringify(schedule),
  });
}

export async function fetchStrategies(): Promise<StrategiesInfo> {
  requireBackend();
  return getJson<StrategiesInfo>('/api/strategies');
}

export async function createStrategy(name: string, body: string): Promise<StrategiesInfo> {
  requireBackend();
  return request<StrategiesInfo>('/api/strategies', {
    method: 'POST',
    body: JSON.stringify({ name, body }),
  });
}

export async function updateStrategy(
  id: string,
  name: string,
  body: string,
): Promise<StrategiesInfo> {
  requireBackend();
  return request<StrategiesInfo>(`/api/strategies/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify({ name, body }),
  });
}

/** Retires a strategy. The server archives rather than deletes, so past
 *  predictions keep their label. */
export async function archiveStrategy(id: string): Promise<StrategiesInfo> {
  requireBackend();
  return request<StrategiesInfo>(`/api/strategies/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
}

export async function activateStrategy(id: string): Promise<StrategiesInfo> {
  requireBackend();
  return request<StrategiesInfo>(`/api/strategies/${encodeURIComponent(id)}/activate`, {
    method: 'POST',
  });
}

export async function registerPushToken(token: string, platform?: string): Promise<void> {
  requireBackend();
  await request('/api/push/register', {
    method: 'POST',
    body: JSON.stringify({ token, platform }),
  });
}
