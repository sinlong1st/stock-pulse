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

  // Tolerate a trailing slash on the base URL (Tailscale prints one).
  const base = API_BASE_URL.replace(/\/+$/, '');
  const url = `${base}/api/feed?limit=${limit}`;

  let res: Response;
  try {
    res = await fetch(url, { headers: { Authorization: `Bearer ${API_TOKEN}` } });
  } catch {
    // fetch throws only on a network-level failure (unreachable host, DNS, TLS).
    throw new Error(`Can't reach ${base} — is Tailscale ON and the URL right?`);
  }
  if (res.status === 401) {
    throw new Error('401 Unauthorized — API token doesn’t match the server.');
  }
  if (!res.ok) {
    throw new Error(`Server returned ${res.status} at ${url}`);
  }
  const data = (await res.json()) as { alerts?: Alert[] };
  return data.alerts ?? [];
}
