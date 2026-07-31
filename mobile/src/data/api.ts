/**
 * Feed data source. Uses the real backend when `API_BASE_URL` is set in
 * config.ts; otherwise returns bundled mock data so the app always renders.
 */
import { API_BASE_URL, API_TOKEN } from '../config';
import { mockAlerts } from './mock';
import { Alert } from './types';

/** True when no backend is configured (the app is showing sample data). */
export const usingMockData = !API_BASE_URL;

export async function fetchFeed(limit = 30): Promise<Alert[]> {
  if (!API_BASE_URL) return mockAlerts;

  const res = await fetch(`${API_BASE_URL}/api/feed?limit=${limit}`, {
    headers: { Authorization: `Bearer ${API_TOKEN}` },
  });
  if (!res.ok) {
    throw new Error(`Feed request failed (${res.status})`);
  }
  const data = (await res.json()) as { alerts?: Alert[] };
  return data.alerts ?? [];
}
