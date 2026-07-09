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
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

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
