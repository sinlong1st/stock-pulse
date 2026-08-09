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
  // Covers each display branch: upcoming, estimated date, already reported, and
  // no date at all. Quarter ends are real quarter boundaries, not report days.
  earnings: [
    {
      ticker: 'MU',
      nextDate: '2026-08-06',
      daysUntil: 2,
      nextIsEstimate: false,
      quarterEnd: '2026-03-31',
      epsActual: 1.34,
      epsEstimate: 1.19,
      surprisePct: 12.6,
      verdict: 'beat' as const,
    },
    {
      ticker: 'NVDA',
      nextDate: '2026-08-27',
      daysUntil: 23,
      nextIsEstimate: true,
      quarterEnd: '2026-06-30',
      epsActual: 0.89,
      epsEstimate: 0.92,
      surprisePct: -3.3,
      verdict: 'miss' as const,
    },
    {
      ticker: 'SPCX',
      nextDate: '2026-08-04',
      daysUntil: -1, // Yahoo still returns the date they just reported on
      quarterEnd: '2026-06-30',
      epsActual: -0.09,
      epsEstimate: -0.29,
      surprisePct: 68.9,
      verdict: 'beat' as const,
    },
    {
      ticker: 'SMCI',
      nextDate: null,
      daysUntil: null,
      quarterEnd: '2026-06-30',
      epsActual: 0.62,
      epsEstimate: 0.62,
      surprisePct: 0,
      verdict: 'inline' as const,
    },
  ],
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
    risks: [
      'NAND pricing has rolled over twice this cycle after similar bounces.',
      'A large share of revenue sits with two hyperscaler customers.',
    ],
  },
  evidence: {
    rangeLow: 52.8,
    rangeHigh: 78.4,
    discountLevel: 'cheap' as const,
    trend: 'down' as const,
    nearestSupport: 63.0,
    supportPct: -3.4,
    resistance: 69.8,
    targetPct: 7.0,
    rewardRisk: 2.1,
    invalidation: 60.0,
    earningsInDays: 7,
    newsCount: 4,
    enoughHistory: true,
  },
  confidence: {
    agree: 2,
    total: 3,
    lean: 'bounce' as const,
    signalsConflict: true,
  },
  analysis: {
    requested: 'both',
    effective: 'both',
    primary: 'openai',
    second: 'deepseek',
    downgraded: false,
  },
  secondOpinion: {
    provider: 'deepseek',
    entry: 'wait' as const,
    note: 'Agrees the setup is constructive but wants to see the $63 support hold before committing.',
    horizons: [
      { horizon: '1w', lean: 'hold' as const, confidence: 'low' },
      { horizon: '1mo', lean: 'bounce' as const, confidence: 'low' },
      { horizon: '3mo', lean: 'bounce' as const, confidence: 'medium' },
    ],
    agrees: false,
    // The common real-world case: the old boolean called this a flat
    // disagreement, but the two reads point the same way and differ only on the
    // entry grade.
    agreement: {
      actionAgreement: 'partial' as const,
      directionAgreement: true,
      confidenceSteps: 1,
      requiresDebate: false,
      differences: [{ code: 'entry-differs', params: { primary: 'fair', second: 'wait' } }],
    },
  },
  rules: {
    original: 'good' as const,
    final: 'fair' as const,
    overridden: true,
    // Annotated because TS would otherwise union the two param shapes and
    // decide `{}` isn't a Record<string, number>.
    findings: [
      { code: 'earnings-imminent', params: { days: 7 } },
      { code: 'high-volatility', params: {} },
    ] as { code: string; params: Record<string, number> }[],
  },
  support: {
    near: 63.0,
    long: 60.0,
    nearLevels: [63.0, 61.5, 60.0],
    longLevels: [58.2, 55.4, 52.8],
  },
  earnings: {
    ticker: 'WDC',
    nextDate: '2026-08-11',
    daysUntil: 7,
    nextIsEstimate: false,
    quarterEnd: '2026-06-30',
    epsActual: 1.72,
    epsEstimate: 1.55,
    surprisePct: 11.0,
    verdict: 'beat' as const,
  },
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
  // Covers both display branches: a solid record, and a thin one that must not
  // be presented as a winner despite the higher percentage.
  strategies: [
    {
      id: 's_deepvalue',
      name: 'Deep value',
      builtin: false,
      total: 24,
      hits: 15,
      misses: 6,
      flats: 3,
      accuracyPct: 71.4,
      avgReturnPct: 2.1,
      pending: 6,
      enoughData: true,
    },
    {
      id: 'default',
      name: 'StockPulse Balanced',
      builtin: true,
      total: 31,
      hits: 16,
      misses: 11,
      flats: 4,
      accuracyPct: 59.3,
      avgReturnPct: 1.2,
      pending: 5,
      enoughData: true,
    },
    {
      id: 's_momentum',
      name: 'Momentum only',
      builtin: false,
      total: 3,
      hits: 3,
      misses: 0,
      flats: 0,
      accuracyPct: 100,
      avgReturnPct: 5.5,
      pending: 9,
      enoughData: false,
    },
  ],
  providers: [
    {
      provider: 'openai',
      total: 28,
      hits: 15,
      misses: 8,
      flats: 5,
      accuracyPct: 65.2,
      pending: 6,
      enoughData: true,
    },
    {
      provider: 'deepseek',
      total: 26,
      hits: 12,
      misses: 10,
      flats: 4,
      accuracyPct: 54.5,
      pending: 6,
      enoughData: true,
    },
  ],
  minMeaningfulCalls: 10,
  recent: [
    { ticker: 'MSFT', sentiment: 'BULLISH' as const, horizon: '5d', returnPct: 4.1, outcome: 'HIT' },
    { ticker: 'NVDA', sentiment: 'BEARISH' as const, horizon: '5d', returnPct: -3.2, outcome: 'HIT' },
    { ticker: 'WDC', sentiment: 'BULLISH' as const, horizon: '1d', returnPct: -0.6, outcome: 'MISS' },
    { ticker: 'MU', sentiment: 'NEUTRAL' as const, horizon: '5d', returnPct: 0.2, outcome: 'FLAT' },
  ],
};
