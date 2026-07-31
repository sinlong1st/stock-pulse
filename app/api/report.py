"""Generate a market briefing on-demand and return it as JSON for the app.

Reuses the exact briefing pipeline the scheduled reports + `/report` use, but
with `deliver=False` so it returns the result instead of sending to Telegram.
Each call is one OpenAI request, so the app triggers it on a button, not on
every screen view.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.api.watchlist import build_watchlist
from app.config import Settings
from app.jobs.briefing import run_report

_DIRECTION_TO_SENTIMENT = {"bullish": "BULLISH", "bearish": "BEARISH", "mixed": "NEUTRAL"}


async def build_report(settings: Settings, *, query: str | None = None) -> dict:
    """Run a briefing and shape it for the mobile Report screen."""
    run = await run_report(query, deliver=False, settings=settings)
    result = run.result

    watchlist = await build_watchlist(settings)
    generated_at = datetime.now(UTC).isoformat()

    if result is None:
        return {
            "takeaway": "",
            "sections": [],
            "watchlist": watchlist,
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
        "generatedAt": generated_at,
        "note": None,
    }
