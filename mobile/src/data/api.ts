/**
 * Feed data source. Uses the real backend when `API_BASE_URL` is set in
 * config.ts; otherwise returns bundled mock data so the app always renders.
 */
import { API_BASE_URL, API_TOKEN } from '../config';
import { mockAlerts, mockReport, mockWatchlist } from './mock';
import { Alert, Report, WatchRow } from './types';

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
export type SettingsInfo = { language: string; languageCode: string | null; languages: Language[] };

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
