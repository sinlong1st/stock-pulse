"""Generate a market briefing on-demand and return it as JSON for the app.

Reuses the exact briefing pipeline the scheduled reports + `/report` use, but
with `deliver=False` so it returns the result instead of sending to Telegram.
Each call is one OpenAI request, so the app triggers it on a button, not on
every screen view.
"""

from __future__ import annotations

from datetime import UTC, datetime

import logging

from app.api.watchlist import build_watchlist
from app.briefing.focus import resolve_focus
from app.commands.symbols import resolve_symbol
from app.config import Settings
from app.earnings import fetch_many, local_today
from app.jobs.briefing import run_report

logger = logging.getLogger("stockpulse.api.report")

_DIRECTION_TO_SENTIMENT = {"bullish": "BULLISH", "bearish": "BEARISH", "mixed": "NEUTRAL"}


async def _resolve_ticker(query: str, settings: Settings) -> tuple[str | None, str | None]:
    """Watchlist match first (typo-tolerant), then a Yahoo symbol search — same
    order the prediction service uses, so both features resolve names alike."""
    target = resolve_focus(query)
    if target.ticker:
        return target.ticker, target.name
    try:
        found = await resolve_symbol(query, settings=settings)
    except Exception:
        logger.debug("Symbol search failed for %r", query, exc_info=True)
        return None, None
    return found if found else (None, None)


async def _price_rows(settings: Settings, query: str | None) -> list[dict]:
    """Prices to show under the report. A focused single-stock report prices only
    that stock — the whole watchlist is noise when you asked about one name. The
    stock need not be on the watchlist."""
    if not query or not query.strip():
        return await build_watchlist(settings)

    ticker, name = await _resolve_ticker(query, settings)
    if not ticker:
        return []  # asked about one stock, but we couldn't pin it to a ticker
    rows = await build_watchlist(settings, tickers=[ticker])
    # Off-watchlist tickers have no alias, so build_watchlist names them after
    # the symbol; the resolved target usually knows the real company name.
    for row in rows:
        if name and row.get("name") == row.get("ticker"):
            row["name"] = name
    return rows


async def _earnings_rows(settings: Settings, watchlist: list[dict]) -> list[dict]:
    """Earnings for whatever the report is priced against — the whole watchlist,
    or the single focused stock. Sorted soonest-first so the next report to
    worry about is at the top; tickers with nothing known are dropped."""
    tickers = [r["ticker"] for r in watchlist if r.get("ticker")]
    found = await fetch_many(tickers, settings=settings)
    today = local_today(settings)
    rows = [found[t].as_dict(today) for t in tickers if t in found]

    def order(row: dict) -> tuple[int, int]:
        """Upcoming reports first (soonest first), then ones that just happened
        (most recent first), then anything with no date at all."""
        days = row["daysUntil"]
        if days is None:
            return (2, 0)
        if days >= 0:
            return (0, days)
        return (1, -days)

    return sorted(rows, key=order)


async def build_report(settings: Settings, *, query: str | None = None) -> dict:
    """Run a briefing and shape it for the mobile Report screen."""
    run = await run_report(query, deliver=False, settings=settings)
    result = run.result

    watchlist = await _price_rows(settings, query)
    earnings = await _earnings_rows(settings, watchlist)
    generated_at = datetime.now(UTC).isoformat()

    if result is None:
        return {
            "takeaway": "",
            "sections": [],
            "watchlist": watchlist,
            "earnings": earnings,
            "generatedAt": generated_at,
            "note": run.skipped_reason or "No report available right now.",
        }

    sections = [
        {
            "title": theme.theme,
            "sentiment": _DIRECTION_TO_SENTIMENT.get(theme.direction, "NEUTRAL"),
            "body": theme.insight,
        }
        for theme in result.themes
    ]
    return {
        "takeaway": result.headline,
        "sections": sections,
        "watchlist": watchlist,
        "earnings": earnings,
        "generatedAt": generated_at,
        "note": None,
    }
