/**
 * Feed data source. Uses the real backend when `API_BASE_URL` is set in
 * config.ts; otherwise returns bundled mock data so the app always renders.
 */
import { API_BASE_URL, API_TOKEN } from '../config';
import { mockAlerts, mockEvaluation, mockPrediction, mockReport, mockWatchlist } from './mock';
import { Alert, Report, Sentiment, WatchRow } from './types';

/** True when no backend is configured (the app is showing sample data). */
export const usingMockData = !API_BASE_URL;

const base = () => API_BASE_URL.replace(/\/+$/, '');

function requireBackend() {
  if (!API_BASE_URL) throw new Error('No backend configured (running on sample data).');
}

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
  } catch {
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

const getJson = <T>(path: string) => request<T>(path);

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
export async function fetchReport(query?: string): Promise<Report> {
  if (!API_BASE_URL) return mockReport;
  const q = query?.trim() ? `?q=${encodeURIComponent(query.trim())}` : '';
  return getJson<Report>(`/api/report${q}`);
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
export type EvalReport = {
  totalEvaluated: number;
  accuracyPct: number | null;
  pending: number;
  bullish: EvalStat;
  bearish: EvalStat;
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
  strategy?: { id: string; name: string; body: string };
  series?: { closes: number[]; volumes: number[]; dates?: string[] };
  language?: string;
  disclaimer?: string;
};

export async function fetchPrediction(query: string): Promise<Prediction> {
  if (!API_BASE_URL) return mockPrediction;
  return getJson<Prediction>(`/api/predict?q=${encodeURIComponent(query.trim())}`);
}

export async function registerPushToken(token: string, platform?: string): Promise<void> {
  requireBackend();
  await request('/api/push/register', {
    method: 'POST',
    body: JSON.stringify({ token, platform }),
  });
}
