"""Earnings calendar + last-quarter results from Yahoo's quoteSummary endpoint.

Answers two questions per ticker: **when does it next report**, and **how did the
last report go** (EPS actual vs estimate, and the surprise).

Unofficial and keyless, like the price/chart source — but unlike the chart
endpoint, quoteSummary is cookie-gated: you must collect a Yahoo cookie, trade it
for a "crumb", and pass that with every call. The crumb is cached and refreshed
automatically when it expires (Yahoo answers 401).

**Strictly best-effort.** Every failure path returns None so a Yahoo change can
degrade the earnings section to "hidden" but can never break a briefing or a
prediction. Results are cached (earnings move quarterly, not intraday) so a
watchlist report doesn't hammer the endpoint.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx

from zoneinfo import ZoneInfo

from app.config import Settings, get_settings, resolve_briefing_timezone

logger = logging.getLogger("stockpulse.earnings")

# A browser-ish UA — Yahoo serves the crumb flow differently to obvious bots.
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class Earnings:
    """What we know about one ticker's earnings, all fields optional."""

    ticker: str
    next_date: date | None = None
    last_date: date | None = None
    eps_actual: float | None = None
    eps_estimate: float | None = None
    surprise_pct: float | None = None

    @property
    def verdict(self) -> str | None:
        """beat / miss / inline — how the last quarter landed vs expectations."""
        if self.eps_actual is None or self.eps_estimate is None:
            return None
        if self.eps_estimate == 0:
            return "inline"
        diff = (self.eps_actual - self.eps_estimate) / abs(self.eps_estimate)
        if diff >= 0.02:
            return "beat"
        if diff <= -0.02:
            return "miss"
        return "inline"

    def days_until(self, today: date | None = None) -> int | None:
        """Days to the next report, counted from `today`.

        Pass the *user's* today — counting from UTC would read a day short all
        evening for anyone west of Greenwich (the user is in Pacific).
        """
        if self.next_date is None:
            return None
        return (self.next_date - (today or datetime.now(tz=UTC).date())).days

    def as_dict(self, today: date | None = None) -> dict:
        return {
            "ticker": self.ticker,
            "nextDate": self.next_date.isoformat() if self.next_date else None,
            "daysUntil": self.days_until(today),
            "lastDate": self.last_date.isoformat() if self.last_date else None,
            "epsActual": self.eps_actual,
            "epsEstimate": self.eps_estimate,
            "surprisePct": round(self.surprise_pct * 100, 1)
            if self.surprise_pct is not None
            else None,
            "verdict": self.verdict,
        }

    @property
    def is_empty(self) -> bool:
        """Nothing worth showing — the caller should drop this row."""
        return self.next_date is None and self.eps_actual is None


def local_today(settings: Settings | None = None) -> date:
    """Today in the user's configured timezone — the reference for countdowns."""
    settings = settings or get_settings()
    try:
        tz = ZoneInfo(resolve_briefing_timezone(settings))
    except Exception:  # unknown tz name in config — UTC is a safe fallback
        return datetime.now(tz=UTC).date()
    return datetime.now(tz=tz).date()


def _raw(node: object) -> float | None:
    """Yahoo wraps numbers as {'raw': 1.23, 'fmt': '1.23'} — or omits them."""
    if isinstance(node, dict):
        value = node.get("raw")
        return float(value) if isinstance(value, (int, float)) else None
    if isinstance(node, (int, float)):
        return float(node)
    return None


def _to_date(node: object) -> date | None:
    epoch = _raw(node)
    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(epoch, tz=UTC).date()
    except (OverflowError, OSError, ValueError):
        return None


def _parse(ticker: str, result: dict) -> Earnings:
    calendar = ((result.get("calendarEvents") or {}).get("earnings")) or {}
    # earningsDate is a list; two entries mean Yahoo only knows a window, so take
    # the start — an approximate date is still more useful than none.
    dates = calendar.get("earningsDate") or []
    next_date = _to_date(dates[0]) if dates else None

    history = (result.get("earningsHistory") or {}).get("history") or []
    last = history[-1] if history else {}
    return Earnings(
        ticker=ticker,
        next_date=next_date,
        last_date=_to_date(last.get("quarter")),
        eps_actual=_raw(last.get("epsActual")),
        eps_estimate=_raw(last.get("epsEstimate")),
        surprise_pct=_raw(last.get("surprisePercent")),
    )


class EarningsClient:
    """Fetches earnings for a ticker, managing Yahoo's cookie/crumb session."""

    def __init__(
        self,
        *,
        base_url: str = "https://query2.finance.yahoo.com",
        cookie_url: str = "https://fc.yahoo.com",
        timeout: float = 10.0,
        cache_ttl: float = 6 * 3600,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.cookie_url = cookie_url
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self._transport = transport
        self._crumb: str | None = None
        self._cookies: httpx.Cookies | None = None
        self._cache: dict[str, tuple[float, Earnings]] = {}
        self._lock = asyncio.Lock()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.timeout,
            transport=self._transport,
            headers={"User-Agent": _UA},
            follow_redirects=True,
            cookies=self._cookies,
        )

    async def _ensure_crumb(self, *, force: bool = False) -> str | None:
        """Get (or refresh) the crumb. One flight at a time — a watchlist report
        fans out concurrently and would otherwise stampede the handshake."""
        async with self._lock:
            if self._crumb and not force:
                return self._crumb
            try:
                async with self._client() as client:
                    # This 404s by design; we only want the Set-Cookie it carries.
                    await client.get(self.cookie_url)
                    self._cookies = client.cookies
                    resp = await client.get(f"{self.base_url}/v1/test/getcrumb")
                    resp.raise_for_status()
                    crumb = resp.text.strip()
            except httpx.HTTPError as exc:
                logger.warning("Yahoo crumb handshake failed: %s", exc)
                return None
            if not crumb or len(crumb) > 32:  # a crumb is a short token, not HTML
                logger.warning("Yahoo returned an implausible crumb; skipping earnings")
                return None
            self._crumb = crumb
            return crumb

    async def _get(self, ticker: str, crumb: str) -> httpx.Response | None:
        try:
            async with self._client() as client:
                return await client.get(
                    f"{self.base_url}/v10/finance/quoteSummary/{ticker}",
                    params={
                        "modules": "calendarEvents,earningsHistory",
                        "crumb": crumb,
                    },
                )
        except httpx.HTTPError as exc:
            logger.warning("Earnings fetch failed for %s: %s", ticker, exc)
            return None

    async def fetch(self, ticker: str) -> Earnings | None:
        """Earnings for one ticker, or None when unavailable. Never raises."""
        cached = self._cache.get(ticker)
        if cached and time.monotonic() - cached[0] < self.cache_ttl:
            return cached[1]

        crumb = await self._ensure_crumb()
        if crumb is None:
            return None

        resp = await self._get(ticker, crumb)
        if resp is not None and resp.status_code == 401:
            # Crumb/cookie went stale — redo the handshake once and retry.
            crumb = await self._ensure_crumb(force=True)
            resp = await self._get(ticker, crumb) if crumb else None

        if resp is None or resp.status_code != 200:
            if resp is not None:
                logger.info("Earnings unavailable for %s (HTTP %s)", ticker, resp.status_code)
            return None

        try:
            payload = resp.json()
            results = ((payload or {}).get("quoteSummary") or {}).get("result") or []
        except ValueError:
            logger.warning("Earnings response for %s was not JSON", ticker)
            return None
        if not results:
            return None

        earnings = _parse(ticker, results[0])
        self._cache[ticker] = (time.monotonic(), earnings)
        return earnings


_client: EarningsClient | None = None


def get_earnings_client(settings: Settings | None = None) -> EarningsClient | None:
    """Shared client, or None when the feature is switched off."""
    global _client
    settings = settings or get_settings()
    if not settings.earnings_enabled:
        return None
    if _client is None:
        _client = EarningsClient(
            base_url=settings.yahoo_quote_summary_url,
            cache_ttl=settings.earnings_cache_hours * 3600,
        )
    return _client


async def fetch_many(
    tickers: list[str],
    *,
    settings: Settings | None = None,
    client: EarningsClient | None = None,
) -> dict[str, Earnings]:
    """Earnings for several tickers concurrently. Missing ones are simply absent."""
    settings = settings or get_settings()
    client = client or get_earnings_client(settings)
    if client is None or not tickers:
        return {}

    capped = tickers[: settings.earnings_max_tickers]

    async def one(ticker: str) -> tuple[str, Earnings | None]:
        try:
            return ticker, await client.fetch(ticker)
        except Exception:  # a bad payload must never sink the whole report
            logger.debug("Earnings lookup crashed for %s", ticker, exc_info=True)
            return ticker, None

    pairs = await asyncio.gather(*[one(t) for t in capped])
    return {t: e for t, e in pairs if e is not None and not e.is_empty}
