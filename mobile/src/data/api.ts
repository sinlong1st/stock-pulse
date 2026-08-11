/**
 * Feed data source. Uses the real backend when `API_BASE_URL` is set in
 * config.ts; otherwise returns bundled mock data so the app always renders.
 */
import { API_BASE_URL, API_TOKEN } from '../config';
import { mockAlerts, mockEvaluation, mockPrediction, mockReport, mockWatchlist } from './mock';
import { SseRequest, streamSse } from './sse';
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
  /** Accuracy per model — "does the second opinion actually help?". */
  providers?: {
    provider: string;
    total: number;
    hits: number;
    misses: number;
    flats: number;
    accuracyPct: number | null;
    pending: number;
    enoughData: boolean;
  }[];
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
  entry?: {
    assessment: 'good' | 'fair' | 'wait';
    note: string;
    risks?: string[]; // stock-specific, AI-written
  };
  /** Checkable facts behind the entry call — arithmetic, not AI. Sent as
   *  numbers so the app can phrase them in the user's language. */
  evidence?: {
    rangeLow: number | null;
    rangeHigh: number | null;
    discountLevel: 'cheap' | 'fair' | 'rich';
    trend: 'up' | 'down' | 'sideways';
    nearestSupport: number | null;
    supportPct: number | null; // signed % from price to that support
    /** Nearest swing high above the price — the reward target. Deliberately not
     *  the range high, which is too far away to be a meaningful target. */
    resistance: number | null;
    targetPct: number | null; // signed % from price to that resistance
    rewardRisk: number | null; // upside / downside, null when not meaningful
    invalidation: number | null; // a close below this breaks the entry thesis
    earningsInDays: number | null;
    newsCount: number;
    enoughHistory: boolean;
  };
  /** Which analyst(s) actually ran. `downgraded` means the requested mode
   *  couldn't be honoured (a missing key) and we fell back. */
  analysis?: {
    requested: string;
    effective: string;
    primary: string;
    second: string | null;
    downgraded: boolean;
  } | null;
  /** An independent read of the same evidence by the other model. Deliberately
   *  kept separate from the main verdict — disagreement is the useful signal. */
  secondOpinion?: {
    provider: string;
    entry: 'good' | 'fair' | 'wait';
    note: string;
    horizons: { horizon: string; lean: Lean; confidence: string }[];
    /** Legacy: entry grades matched, nothing more. Superseded by `agreement`,
     *  kept because the backend still sends it to older app builds. */
    agrees: boolean;
    /** How much the two reads actually line up (backend §11 scoring). Optional
     *  because a droplet running an older build won't send it. */
    agreement?: {
      actionAgreement: 'strong' | 'partial' | 'conflict';
      directionAgreement: boolean;
      confidenceSteps: number;
      requiresDebate: boolean;
      differences: { code: string; params: Record<string, string | number> }[];
    };
  } | null;
  /** Deterministic risk rules applied over the AI's entry call. They only ever
   *  make it more cautious; `findings` explains any downgrade. */
  rules?: {
    original: 'good' | 'fair' | 'wait';
    final: 'good' | 'fair' | 'wait';
    overridden: boolean;
    findings: { code: string; params: Record<string, number> }[];
  };
  /** Why the confidence is what it is. */
  confidence?: {
    agree: number;
    total: number;
    lean: Lean | null;
    signalsConflict: boolean;
  };
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

export async function fetchPrediction(
  query: string,
  signal?: AbortSignal,
  mode?: string,
): Promise<Prediction> {
  if (!API_BASE_URL) return mockPrediction;
  const m = mode ? `&mode=${encodeURIComponent(mode)}` : '';
  return getJson<Prediction>(
    `/api/predict?q=${encodeURIComponent(query.trim())}${m}`,
    signal,
  );
}

// --- which model(s) run ----------------------------------------------------

export type AnalysisMode = 'openai' | 'deepseek' | 'both';
export type ModeInfo = {
  mode: AnalysisMode;
  /** Only the modes a configured key can actually deliver. */
  available: AnalysisMode[];
  providers: string[];
};

export async function fetchMode(signal?: AbortSignal): Promise<ModeInfo> {
  if (!API_BASE_URL) {
    return { mode: 'both', available: ['openai', 'deepseek', 'both'], providers: [] };
  }
  return getJson<ModeInfo>('/api/predict/mode', signal);
}

export async function saveMode(mode: AnalysisMode): Promise<ModeInfo> {
  if (!API_BASE_URL) {
    return { mode, available: ['openai', 'deepseek', 'both'], providers: [] };
  }
  return request<ModeInfo>('/api/predict/mode', {
    method: 'PUT',
    body: JSON.stringify({ mode }),
  });
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
/** Must match EXIT_STAGES in app/position/service.py. */
export const EXIT_STAGES = ['resolve', 'prices', 'news', 'market', 'analyze'];

function streamOrFallback<T, L = unknown>(
  path: string,
  fallback: (signal: AbortSignal) => Promise<T>,
  onStage: (stage: string) => void,
  onDone: (result: T) => void,
  onError: (error: Error) => void,
  onLate?: (payload: L) => void,
  init?: SseRequest,
): StreamHandle {
  let cancelled = false;
  // Cancelling must also stop a fallback request that's already in flight.
  const ctrl = new AbortController();
  const handle = streamSse<T, L>(path, {
    onStage,
    onResult: (result) => !cancelled && onDone(result),
    onLate: (payload) => !cancelled && onLate?.(payload),
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
  }, init);
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

/** Payload of the late `second` event — the slower model's opinion. */
export type SecondOpinionLate = { secondOpinion: Prediction['secondOpinion'] };

/**
 * Forward-looking read, reporting real pipeline stages as they happen.
 *
 * In `both` mode the second opinion arrives *after* the main result (measured
 * live: ~6s vs ~18s), so `onSecond` fires later and the screen fills the card in
 * then. On the fallback path there is no late event — the plain endpoint waits
 * for both and returns them together, which is slower but still correct.
 */
export function streamPrediction(
  query: string,
  onStage: (stage: string) => void,
  onDone: (prediction: Prediction) => void,
  onError: (error: Error) => void,
  options?: { mode?: string; onSecond?: (payload: SecondOpinionLate) => void },
): StreamHandle {
  if (!API_BASE_URL) {
    onDone(mockPrediction);
    return { cancel: () => {} };
  }
  const mode = options?.mode ? `&mode=${encodeURIComponent(options.mode)}` : '';
  const q = `?q=${encodeURIComponent(query.trim())}${mode}`;
  return streamOrFallback<Prediction, SecondOpinionLate>(
    `/api/predict/stream${q}`,
    (signal) => fetchPrediction(query, signal, options?.mode),
    onStage,
    onDone,
    onError,
    options?.onSecond,
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

// --- position exit advisor -------------------------------------------------
//
// The other side of Predict: "I already own this — hold, trim or sell?". Every
// dollar figure here is computed by the backend from real price levels; the AI
// only writes the judgement and the words. See the `advice` block.

export type ExitAction =
  | 'hold'
  | 'hold-with-stop'
  | 'partial-sell'
  | 'take-profit'
  | 'reduce'
  | 'exit'
  | 'sell-into-strength'
  | 'wait-for-confirmation'
  | 'no-clear-edge';

export type PositionSummary = {
  shares: number;
  averageCost: number;
  currentPrice: number;
  costBasis: number;
  currentValue: number;
  unrealizedPnl: number;
  unrealizedPnlPct: number;
  inProfit: boolean;
  status: string;
};

export type GivebackLevel = {
  support: number;
  remainingPnl: number;
  giveback: number;
  givebackPctOfProfit: number | null;
  pctMove: number;
  /** Below the average cost — falling here is a loss, not "giving back profit",
   *  so it must never be phrased as profit-taking (backend RULE-EXIT-011). */
  belowCostBasis: boolean;
};

export type HoldRewardRisk = {
  target: number;
  support: number;
  upsidePerShare: number;
  downsidePerShare: number;
  additionalProfit: number;
  profitGiveback: number;
  ratio: number;
  label: 'strong' | 'attractive' | 'balanced' | 'weak' | 'poor';
};

export type PartialSellOption = {
  pctRequested: number;
  pctActual: number;
  sharesSold: number;
  sharesRemaining: number;
  proceeds: number;
  realizedPnl: number;
  remainingValue: number;
  remainingUnrealizedPnl: number;
  additionalUpsideOnRemaining: number | null;
  possible: boolean;
};

export type ExitScenario = {
  name: 'bull' | 'base' | 'bear';
  probability: number;
  priceRange: { low: number; high: number };
  positionValueRange: { low: number; high: number };
  pnlRange: { low: number; high: number };
  additionalPnlFromCurrentRange: { low: number; high: number };
  trigger?: string;
};

export type ExitPlan = {
  name: 'conservative' | 'balanced' | 'aggressive';
  action: 'hold' | 'partial-sell' | 'sell-all';
  sellPctNow: number | null;
  stop: number | null;
  firstTarget: number | null;
  invalidation: number | null;
  explanation: string;
  sale: PartialSellOption | null;
};

export type ExitAdvice = {
  ok: boolean;
  reason?: string;
  positionId?: string | null;
  ticker?: string;
  name?: string;
  price?: string;
  priceFresh?: string | null;
  position?: PositionSummary;
  giveback?: GivebackLevel[];
  holdRewardRisk?: HoldRewardRisk | null;
  /** The same math against the user's own target, when they set one. Kept
   *  separate from the chart-based reading on purpose. */
  atYourTarget?: HoldRewardRisk | null;
  partialSell?: PartialSellOption[];
  allowPartialSell?: boolean;
  costBasisRecovery?: {
    sharesNeeded: number;
    sharesRemaining: number;
    possible: boolean;
    proceeds: number;
  };
  levels?: {
    nearestSupport: number | null;
    invalidation: number | null;
    resistance: number | null;
    stop: number | null;
    target: number | null;
    /** How far each leg is in ATRs — the context that says how much to trust
     *  the reward/risk ratio. A support under ~0.5 ATR is inside daily noise. */
    distance: { supportAtrs: number | null; resistanceAtrs: number | null; atr14: number | null };
  };
  technicals?: {
    trend: 'up' | 'down' | 'sideways';
    discountLevel: 'cheap' | 'fair' | 'rich';
    rangeNote: string;
    indicators: Record<string, number | null | { histogram?: number }>;
    market: {
      marketTrend: string | null;
      vix: number | null;
      vixRegime: string | null;
      relative20d: number | null;
      riskAppetite: string | null;
    };
  };
  extension?: { aboveSma20Pct: number | null; aboveSma20Atrs: number | null };
  relativeVolume?: number | null;
  earningsInDays?: number | null;
  rules?: {
    original: ExitAction | null;
    final: ExitAction | null;
    overridden: boolean;
    refreshRequired: boolean;
    findings: { code: string; params: Record<string, unknown>; atLeast: string | null }[];
  };
  /** Null when no AI provider is configured — the numbers stand on their own. */
  advice?: {
    action: ExitAction;
    aiAction: ExitAction;
    confidence: 'low' | 'medium' | 'high';
    thesis: string;
    reasonsToHold: string[];
    reasonsToSell: string[];
    warnings: string[];
    provider: string | null;
  } | null;
  scenarios?: ExitScenario[];
  plans?: ExitPlan[];
  series?: { closes: number[]; volumes: number[]; dates?: string[] };
  disclaimer?: string;
};

export type ExitRequestBody = {
  positionId?: string;
  ticker?: string;
  shares?: number;
  averageCost?: number;
  stop?: number | null;
  target?: number | null;
};

export async function fetchExitAdvice(
  body: ExitRequestBody,
  signal?: AbortSignal,
): Promise<ExitAdvice> {
  requireBackend();
  try {
    return await request<ExitAdvice>('/api/positions/exit-advisor', {
      method: 'POST',
      body: JSON.stringify(body),
      signal,
    });
  } catch (e) {
    // A 404 here has exactly one cause worth naming: the endpoint is gated by
    // POSITION_EXIT_ENABLED, and the app ships over the air ahead of the
    // server. "Server returned 404" would send you looking in the wrong place.
    if (e instanceof Error && e.message.includes('404')) {
      throw new Error(
        'The server doesn’t have the exit advisor yet — deploy the backend and set POSITION_EXIT_ENABLED=true.',
      );
    }
    throw e;
  }
}

/**
 * Exit analysis with live stage progress.
 *
 * POSTs rather than GETs: the request is a position, not a query string. Falls
 * back to the plain endpoint on any streaming error, exactly like Report and
 * Predict — a buffering proxy costs the live stages, not the feature.
 */
export function streamExitAdvice(
  body: ExitRequestBody,
  onStage: (stage: string) => void,
  onDone: (advice: ExitAdvice) => void,
  onError: (error: Error) => void,
): StreamHandle {
  return streamOrFallback<ExitAdvice>(
    '/api/positions/exit-advisor/stream',
    (signal) => fetchExitAdvice(body, signal),
    onStage,
    onDone,
    onError,
    undefined,
    { method: 'POST', body },
  );
}

export type SavedPosition = {
  id: string;
  ticker: string;
  shares: number;
  averageCost: number;
  purchaseDate: string | null;
  stop: number | null;
  target: number | null;
  investmentStyle: string;
  riskTolerance: string;
  allowPartialSell: boolean;
  archived: boolean;
  createdAt: string;
  updatedAt: string;
};

export type PositionsInfo = {
  positions: SavedPosition[];
  limits: { maxPositions: number; investmentStyles: string[]; riskTolerances: string[] };
};

export async function fetchPositions(): Promise<PositionsInfo> {
  requireBackend();
  return getJson<PositionsInfo>('/api/positions');
}

export async function savePosition(body: {
  ticker: string;
  shares: number;
  averageCost: number;
  stop?: number | null;
  target?: number | null;
}): Promise<PositionsInfo> {
  requireBackend();
  return request<PositionsInfo>('/api/positions', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** Retires a holding. The server archives rather than deletes, so any past
 *  analysis stays attributable. */
export async function removePosition(id: string): Promise<PositionsInfo> {
  requireBackend();
  return request<PositionsInfo>(`/api/positions/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
}

export async function registerPushToken(token: string, platform?: string): Promise<void> {
  requireBackend();
  await request('/api/push/register', {
    method: 'POST',
    body: JSON.stringify({ token, platform }),
  });
}
