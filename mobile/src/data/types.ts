/** Domain types — mirror the backend's classification/price shapes. */

export type Sentiment = 'BULLISH' | 'BEARISH' | 'NEUTRAL';
export type Importance = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type Category = 'MACRO' | 'TICKER' | 'SECTOR';

export type PriceSnapshot = {
  symbol: string;
  price: string; // pre-formatted for display, e.g. "118.44"
  changePct: number; // signed, vs open
  fresh: string; // "LIVE" or "AS OF FRI 13:00 PDT"
};

export type Alert = {
  id: string;
  importance: Importance;
  category: Category;
  time: string; // relative, e.g. "12m"
  summary: string;
  why: string;
  tickers: string[];
  sentiment: Sentiment;
  price: PriceSnapshot;
  source: string;
};

export type WatchRow = {
  ticker: string;
  name: string;
  price: string;
  changePct: number;
  sentiment: Sentiment;
};

export type ReportSection = {
  title: string;
  sentiment: Sentiment;
  body: string;
};

export type Report = {
  dateLabel: string; // "FRI 30 JUL"
  takeaway: string;
  sections: ReportSection[];
  watchlist: WatchRow[];
  freshness: string;
  footnote: string;
};
