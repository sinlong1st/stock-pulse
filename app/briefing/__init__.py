"""Market Briefing ("the secretary") — a proactive, scheduled/on-demand
analyst that pulls the latest news and reports what matters for the
watchlist. See specs/STOCKPULSE_BRIEFING_PLAN.md.

This is a separate pipeline from the alert flow: fetch fresh → synthesize →
deliver. Step A (this package's `retrieval`) is the fetch + freshness stage;
later steps add the analyst call, delivery, and scheduling.
"""

from app.briefing.analyst import (
    AnalystError,
    MarketAnalyst,
    build_analyst,
    build_system_prompt,
    build_user_message,
)
from app.briefing.memory import ThemeMemory
from app.briefing.models import (
    BriefingResult,
    BriefingTheme,
    WatchlistNote,
)
from app.briefing.retrieval import (
    RetrievalResult,
    RetrievedItem,
    assess_freshness,
    looks_like_recap,
    retrieve_fresh_news,
)

__all__ = [
    "RetrievalResult",
    "RetrievedItem",
    "assess_freshness",
    "looks_like_recap",
    "retrieve_fresh_news",
    "AnalystError",
    "MarketAnalyst",
    "build_analyst",
    "build_system_prompt",
    "build_user_message",
    "BriefingResult",
    "BriefingTheme",
    "WatchlistNote",
    "ThemeMemory",
]
