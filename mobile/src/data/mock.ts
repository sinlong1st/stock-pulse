/**
 * Mock data for the design-faithful prototype. Swap this module for real API
 * calls once the multi-tenant backend + JSON endpoints exist (see
 * specs/STOCKPULSE_MOBILE_APP_PLAN.md, Phase 1).
 */
import { Alert, Report, WatchRow } from './types';

export const mockAlerts: Alert[] = [
  {
    id: '1',
    importance: 'CRITICAL',
    category: 'TICKER',
    time: '12m',
    summary: 'Nvidia slips as U.S. weighs fresh curbs on H20 accelerator exports to China.',
    why: 'A Commerce review could delay $4–5B of shipments into next quarter — consensus data-center revenue may be 6–8% too high.',
    tickers: ['NVDA', 'TSM', 'AMD'],
    sentiment: 'BEARISH',
    price: { symbol: 'NVDA', price: '118.44', changePct: -4.2, fresh: 'AS OF FRI 13:00 PDT' },
    source: 'Reuters · Fri 12:48 PDT',
  },
  {
    id: '2',
    importance: 'MEDIUM',
    category: 'TICKER',
    time: '48m',
    summary: 'Microsoft surges as Azure growth beats forecasts on strong AI demand.',
    why: 'Cloud strength signals durable enterprise AI spend, a positive read-through for the whole hyperscaler group.',
    tickers: ['MSFT'],
    sentiment: 'BULLISH',
    price: { symbol: 'MSFT', price: '512.30', changePct: 15.0, fresh: 'AS OF FRI 13:00 PDT' },
    source: 'Yahoo Finance · Fri 12:12 PDT',
  },
  {
    id: '3',
    importance: 'MEDIUM',
    category: 'MACRO',
    time: '1h',
    summary: 'Mortgage rates hit a one-year high on war and inflation concerns.',
    why: 'Higher rates dampen housing and consumer spending — a mild drag on growth-sensitive names.',
    tickers: [],
    sentiment: 'BEARISH',
    price: { symbol: 'QQQ', price: '486.10', changePct: -0.8, fresh: 'AS OF FRI 13:00 PDT' },
    source: 'NPR via Google News · Fri 11:56 PDT',
  },
  {
    id: '4',
    importance: 'LOW',
    category: 'SECTOR',
    time: '2h',
    summary: 'Storage names firm as memory pricing chatter turns constructive.',
    why: 'Supplier commentary hints at tightening NAND supply into year-end — supportive for WDC and MU.',
    tickers: ['WDC', 'MU'],
    sentiment: 'NEUTRAL',
    price: { symbol: 'WDC', price: '65.20', changePct: 0.3, fresh: 'AS OF FRI 13:00 PDT' },
    source: 'Bloomberg · Fri 10:40 PDT',
  },
];

export const mockWatchlist: WatchRow[] = [
  { ticker: 'NVDA', name: 'NVIDIA Corp', price: '118.44', changePct: -4.2, sentiment: 'BEARISH' },
  { ticker: 'MSFT', name: 'Microsoft Corp', price: '512.30', changePct: 15.0, sentiment: 'BULLISH' },
  { ticker: 'WDC', name: 'Western Digital', price: '65.20', changePct: 0.3, sentiment: 'NEUTRAL' },
  { ticker: 'MU', name: 'Micron Technology', price: '104.80', changePct: 1.1, sentiment: 'BULLISH' },
  { ticker: 'SMCI', name: 'Super Micro Computer', price: '44.10', changePct: 0.2, sentiment: 'NEUTRAL' },
];

export const mockReport: Report = {
  takeaway:
    "Rates are back in the driver's seat. AI hardware wobbles on China risk; software and storage hold up.",
  sections: [
    {
      title: 'AI & semiconductors',
      sentiment: 'BEARISH',
      body: 'Export-curb headlines pressure NVDA and the supply chain (TSM, AMD). Base case is a licensing framework, not an outright ban.',
    },
    {
      title: 'Software & cloud',
      sentiment: 'BULLISH',
      body: 'Azure’s beat reinforces durable enterprise AI spend; MSFT leads, a positive read-through for the group.',
    },
    {
      title: 'Macro & Fed',
      sentiment: 'NEUTRAL',
      body: 'Rates at a one-year high complicate the soft-landing story, but no policy surprise this week.',
    },
  ],
  watchlist: mockWatchlist,
  note: null,
};

export const mockPrediction = {
  ok: true,
  ticker: 'WDC',
  name: 'Western Digital',
  price: '65.20',
  priceFresh: 'AS OF FRI 13:00 PDT',
  discount: {
    level: 'fair' as const,
    vsRangeNote: '18% above the 6-month low, 30% below the high',
    note: 'Near the middle of its 6-month range.',
  },
  trend: 'down' as const,
  enoughHistory: true,
  horizons: [
    { horizon: '1w', lean: 'hold' as const, confidence: 'low' as const, rationale: 'No fresh catalyst; likely range-bound near term.' },
    { horizon: '1mo', lean: 'dip' as const, confidence: 'medium' as const, rationale: 'The downtrend may persist while it sits mid-range.' },
    { horizon: '3mo', lean: 'bounce' as const, confidence: 'low' as const, rationale: 'Value could firm up if memory pricing improves.' },
  ],
  drivers: ['Downward price trend', 'Middle of 6-month range', 'Thin fresh news'],
  entry: {
    assessment: 'fair' as const,
    note: 'A fair entry here, but not a screaming buy while the trend is soft. A pullback toward the $63 near support would be a better spot, and $60 marks the longer-term floor to watch.',
  },
  support: { near: 63.0, long: 60.0 },
  series: {
    closes: [72, 74, 71, 69, 70, 68, 66, 67, 65, 63, 64, 62, 60, 61, 63, 64, 66, 65, 66, 65.2],
    volumes: [12, 9, 14, 20, 11, 8, 25, 13, 10, 30, 12, 9, 18, 7, 22, 14, 11, 9, 16, 13],
    dates: Array.from({ length: 20 }, (_, i) => {
      const d = new Date(2026, 6, 1 + i);
      return d.toISOString().slice(0, 10);
    }),
  },
  strategy: {
    id: 'default',
    name: 'StockPulse Balanced',
    body: 'Weigh recent news, the price trend, and where the price sits in its range. A big discount can set up a bounce, but a falling trend can keep falling. Prefer "hold" with low confidence when signals conflict.',
  },
  disclaimer: 'AI opinion — not investment advice.',
};

export const mockEvaluation = {
  totalEvaluated: 128,
  accuracyPct: 74,
  pending: 9,
  bullish: { accuracyPct: 81, hits: 46, misses: 11, total: 61, avgReturnPct: 2.4 },
  bearish: { accuracyPct: 69, hits: 29, misses: 13, total: 48, avgReturnPct: -1.8 },
  recent: [
    { ticker: 'MSFT', sentiment: 'BULLISH' as const, horizon: '5d', returnPct: 4.1, outcome: 'HIT' },
    { ticker: 'NVDA', sentiment: 'BEARISH' as const, horizon: '5d', returnPct: -3.2, outcome: 'HIT' },
    { ticker: 'WDC', sentiment: 'BULLISH' as const, horizon: '1d', returnPct: -0.6, outcome: 'MISS' },
    { ticker: 'MU', sentiment: 'NEUTRAL' as const, horizon: '5d', returnPct: 0.2, outcome: 'FLAT' },
  ],
};
