"""Price data client (Alpaca Market Data API).

Isolated behind a `PriceClient` interface, like the classifier and notifier,
so the provider can be swapped later. Used for price context in alerts now,
and as the data source for the self-evaluation loop later.

Best-effort by design: `latest_price` / `change_today` return ``None`` on
any error or missing data (a private ticker like SPCX has no price), so the
alert path never crashes over prices. `bars` raises on error for callers
that need to know.
"""

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger("stockpulse.prices")


class PriceError(Exception):
    """Raised when price data cannot be retrieved (for strict callers)."""


@dataclass
class PriceMove:
    ticker: str
    price: float
    prev_close: float
    change_pct: float


@dataclass
class PriceSnapshot:
    """A fuller point-in-time price read for a ticker.

    ``price_time`` is when the last trade actually happened — the honest answer
    to "is this current?". Outside market hours it will be stale (the last
    print), because the stock simply isn't trading.
    """

    ticker: str
    price: float
    price_time: datetime | None  # timestamp of the last trade (UTC)
    open: float | None  # today's regular-session open
    prev_close: float | None

    @property
    def change_from_open_pct(self) -> float | None:
        if self.open:
            return (self.price - self.open) / self.open * 100
        return None

    @property
    def change_from_prev_pct(self) -> float | None:
        if self.prev_close:
            return (self.price - self.prev_close) / self.prev_close * 100
        return None


def _parse_ts(value: str | None) -> datetime | None:
    """Parse an Alpaca RFC3339 timestamp (nanosecond precision, trailing Z)."""
    if not value:
        return None
    v = value.strip().replace("Z", "+00:00")
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(.*)$", v)
    if m:
        base, frac, tz = m.groups()
        v = base + (f".{frac[:6]}" if frac else "") + (tz or "")
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        return None


def price_freshness(
    price_time: datetime | None,
    *,
    now: datetime | None = None,
    tz_name: str = "UTC",
    language: str = "English",
    live_within_min: float = 15.0,
) -> str:
    """Honest freshness label: 'live' if very recent, else the last-trade time.

    Avoids pretending a stale overnight/weekend print is a current price.
    """
    vi = language.strip().lower() == "vietnamese"
    if price_time is None:
        return "mới nhất" if vi else "latest"
    now = now or datetime.now(tz=UTC)
    age_min = (now - price_time).total_seconds() / 60.0
    if age_min <= live_within_min:
        return "trực tiếp" if vi else "live"
    try:
        local = price_time.astimezone(ZoneInfo(tz_name))
    except Exception:
        local = price_time
    stamp = local.strftime("%a %H:%M")
    abbr = local.tzname() or ""
    return (f"lúc {stamp} {abbr}".strip() if vi else f"as of {stamp} {abbr}".strip())


def price_snapshot_line(
    snap: PriceSnapshot,
    *,
    now: datetime | None = None,
    tz_name: str = "UTC",
    language: str = "English",
) -> str:
    """One line: current price (+freshness) and today's open (+change).

    e.g. 'WDC: $65.20 (live) · open $64.10 (+1.7%)'.
    """
    vi = language.strip().lower() == "vietnamese"
    fresh = price_freshness(snap.price_time, now=now, tz_name=tz_name, language=language)
    parts = [f"{snap.ticker}: ${snap.price:,.2f} ({fresh})"]
    if snap.open is not None:
        chg = snap.change_from_open_pct
        chg_str = f" ({chg:+.1f}%)" if chg is not None else ""
        open_word = "mở cửa" if vi else "open"
        parts.append(f"{open_word} ${snap.open:,.2f}{chg_str}")
    return " · ".join(parts)


@dataclass
class Bar:
    t: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class PriceClient(ABC):
    @abstractmethod
    async def latest_price(self, ticker: str) -> float | None: ...

    @abstractmethod
    async def change_today(self, ticker: str) -> PriceMove | None: ...

    async def snapshot(self, ticker: str) -> PriceSnapshot | None:
        """Fuller price read (price + time + open). Default: unsupported."""
        return None


class AlpacaPriceClient(PriceClient):
    """Fetch prices from the Alpaca Market Data API (free IEX feed)."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        *,
        data_url: str = "https://data.alpaca.markets/v2",
        feed: str = "iex",
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key or not secret_key:
            raise PriceError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set.")
        self.api_key = api_key
        self.secret_key = secret_key
        self.data_url = data_url.rstrip("/")
        self.feed = feed
        self.timeout = timeout
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
        }

    async def _get(self, path: str, params: dict) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
            response = await client.get(
                f"{self.data_url}{path}", headers=self._headers(), params=params
            )
            response.raise_for_status()
            return response.json()

    async def _snapshot(self, ticker: str) -> dict | None:
        try:
            return await self._get(f"/stocks/{ticker}/snapshot", {"feed": self.feed})
        except httpx.HTTPError as exc:
            logger.warning("Price snapshot failed for %s: %s", ticker, exc)
            return None

    async def latest_price(self, ticker: str) -> float | None:
        snap = await self._snapshot(ticker)
        if not snap:
            return None
        return (snap.get("latestTrade") or {}).get("p")

    async def change_today(self, ticker: str) -> PriceMove | None:
        snap = await self._snapshot(ticker)
        if not snap:
            return None
        price = (snap.get("latestTrade") or {}).get("p")
        prev_close = (snap.get("prevDailyBar") or {}).get("c")
        if price is None or not prev_close:
            return None
        change_pct = (price - prev_close) / prev_close * 100
        return PriceMove(ticker=ticker, price=price, prev_close=prev_close, change_pct=change_pct)

    async def snapshot(self, ticker: str) -> PriceSnapshot | None:
        snap = await self._snapshot(ticker)
        if not snap:
            return None
        trade = snap.get("latestTrade") or {}
        price = trade.get("p")
        if price is None:
            return None
        return PriceSnapshot(
            ticker=ticker,
            price=price,
            price_time=_parse_ts(trade.get("t")),
            open=(snap.get("dailyBar") or {}).get("o"),
            prev_close=(snap.get("prevDailyBar") or {}).get("c"),
        )


def _epoch_to_dt(value: object) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)  # type: ignore[arg-type]
    except (ValueError, OSError, TypeError):
        return None


class YahooPriceClient(PriceClient):
    """Prices from Yahoo Finance's free v8 chart endpoint.

    Unofficial but keyless, and — unlike the Alpaca free IEX feed (one small
    exchange) — it returns the **consolidated** price and includes pre/post
    market trades, so "current price" is much closer to what a phone stocks app
    shows. It still cannot invent an overnight price (nothing trades then).
    """

    _UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StockPulse/1.0"

    def __init__(
        self,
        *,
        base_url: str = "https://query1.finance.yahoo.com",
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transport = transport

    async def _chart(self, ticker: str) -> dict | None:
        url = f"{self.base_url}/v8/finance/chart/{ticker}"
        params = {"interval": "1m", "range": "1d", "includePrePost": "true"}
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, transport=self._transport
            ) as client:
                resp = await client.get(url, params=params, headers={"User-Agent": self._UA})
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("Yahoo price fetch failed for %s: %s", ticker, exc)
            return None
        results = ((data or {}).get("chart") or {}).get("result") or []
        return results[0] if results else None

    async def snapshot(self, ticker: str) -> PriceSnapshot | None:
        result = await self._chart(ticker)
        if not result:
            return None
        meta = result.get("meta") or {}
        timestamps = result.get("timestamp") or []
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        opens = quote.get("open") or []

        # Current price = the most recent traded bar (includes pre/post market).
        price: float | None = None
        price_time: datetime | None = None
        for ts, close in zip(reversed(timestamps), reversed(closes), strict=False):
            if close is not None:
                price, price_time = close, _epoch_to_dt(ts)
                break
        reg_price = meta.get("regularMarketPrice")
        if price is None:
            price = reg_price
            price_time = _epoch_to_dt(meta.get("regularMarketTime"))
        if price is None:
            return None
        # Guard against a wild thin pre/post-market print: if the latest bar is
        # >15% off the official regular price, trust the official one instead.
        if reg_price and abs(price - reg_price) / reg_price > 0.15:
            price = reg_price
            price_time = _epoch_to_dt(meta.get("regularMarketTime"))

        # Open = first bar of the regular session (skip pre-market bars).
        reg_start = ((meta.get("currentTradingPeriod") or {}).get("regular") or {}).get("start")
        open_price: float | None = None
        for ts, open_val in zip(timestamps, opens, strict=False):
            if open_val is not None and (reg_start is None or ts >= reg_start):
                open_price = open_val
                break

        return PriceSnapshot(
            ticker=ticker,
            price=price,
            price_time=price_time,
            open=open_price,
            prev_close=meta.get("chartPreviousClose") or meta.get("previousClose"),
        )

    async def latest_price(self, ticker: str) -> float | None:
        snap = await self.snapshot(ticker)
        return snap.price if snap else None

    async def change_today(self, ticker: str) -> PriceMove | None:
        snap = await self.snapshot(ticker)
        if not snap or not snap.prev_close:
            return None
        return PriceMove(
            ticker=ticker,
            price=snap.price,
            prev_close=snap.prev_close,
            change_pct=snap.change_from_prev_pct or 0.0,
        )


def price_context_line(move: PriceMove, language: str = "English") -> str:
    """One-line price context for an alert, e.g. '📈 MU +3.4% today'."""
    word = "hôm nay" if language.strip().lower() == "vietnamese" else "today"
    arrow = "📈" if move.change_pct >= 0 else "📉"
    return f"{arrow} {move.ticker} {move.change_pct:+.1f}% {word}"


def build_price_client(settings: Settings | None = None) -> AlpacaPriceClient:
    """Construct the Alpaca price client. Raises if keys are missing."""
    settings = settings or get_settings()
    return AlpacaPriceClient(
        settings.alpaca_api_key,
        settings.alpaca_secret_key,
        data_url=settings.alpaca_data_url,
    )


def maybe_price_client(settings: Settings | None = None) -> PriceClient | None:
    """Build a price client only if price-in-alerts is enabled and configured."""
    settings = settings or get_settings()
    if not (settings.price_features_enabled and settings.price_context_in_alerts):
        return None
    try:
        return build_price_client(settings)
    except PriceError:
        logger.warning("Price context enabled but Alpaca keys missing; skipping.")
        return None


def maybe_briefing_price_client(settings: Settings | None = None) -> PriceClient | None:
    """Build the price client used for the briefing's price display.

    Source is configurable: "yahoo" needs no keys and gives consolidated +
    pre/post-market prices; "alpaca" uses the free IEX feed (needs keys +
    PRICE_FEATURES_ENABLED).
    """
    settings = settings or get_settings()
    if not settings.briefing_prices_in_report:
        return None
    if settings.briefing_price_source.strip().lower() == "yahoo":
        return YahooPriceClient(base_url=settings.yahoo_chart_url)
    if not settings.price_features_enabled:
        return None
    try:
        return build_price_client(settings)
    except PriceError:
        logger.warning("Briefing prices (alpaca) enabled but keys missing; skipping.")
        return None


def maybe_eval_price_client(settings: Settings | None = None) -> PriceClient | None:
    """Build a price client only if self-evaluation is enabled and configured."""
    settings = settings or get_settings()
    if not (settings.price_features_enabled and settings.evaluation_enabled):
        return None
    try:
        return build_price_client(settings)
    except PriceError:
        logger.warning("Evaluation enabled but Alpaca keys missing; skipping predictions.")
        return None
