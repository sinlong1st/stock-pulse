"""Tests for the briefing analyst (Briefing plan, step B).

The OpenAI API is never called for real: a httpx MockTransport returns canned
responses, so the request/parse/validate path runs offline.
"""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.briefing.analyst import (
    AnalystError,
    MarketAnalyst,
    build_system_prompt,
    build_user_message,
)
from app.briefing.models import BriefingResult
from app.briefing.retrieval import RetrievalResult, assess_freshness
from app.models.article import NewsArticle

NOW = datetime(2026, 7, 28, 16, 0, tzinfo=UTC)


def _article(title: str, *, published: datetime | None, summary: str = "snippet") -> NewsArticle:
    return NewsArticle(
        source="Test",
        title=title,
        summary=summary,
        url=f"https://e.com/{title.replace(' ', '-')}",
        published_at=published,
        collected_at=NOW,
        content_hash=title,
    )


def _retrieval(*articles: NewsArticle, window_hours: float = 2.0) -> RetrievalResult:
    fresh, unverified = [], []
    for a in articles:
        item = assess_freshness(a, now=NOW, window_hours=window_hours)
        (fresh if item.within_window else unverified).append(item)
    return RetrievalResult(
        now=NOW,
        window_hours=window_hours,
        fresh=fresh,
        unverified=unverified,
        collected=len(articles),
        stale_dropped=0,
    )


def _openai_response(content: dict | str) -> httpx.Response:
    body = content if isinstance(content, str) else json.dumps(content)
    return httpx.Response(200, json={"choices": [{"message": {"content": body}}]})


def _analyst(handler, **kw) -> MarketAnalyst:
    return MarketAnalyst(
        "test-key",
        model="gpt-4o-mini",
        watchlist=kw.pop("watchlist", ["NVDA", "MSFT"]),
        transport=httpx.MockTransport(handler),
        **kw,
    )


_MATERIAL = {
    "has_material_update": True,
    "urgency": "notable",
    "headline": "AI capex story strengthening",
    "themes": [
        {
            "theme": "AI & semiconductors",
            "direction": "positive",  # synonym -> bullish
            "tickers": ["nvda"],
            "insight": "Hyperscaler capex guides higher.",
            "trend": "strengthening",
            "freshness": "new",
            "event_time": "2026-07-28T15:30",
            "sources": ["Test"],
        }
    ],
    "watchlist_notes": [{"ticker": "nvda", "note": "capex tailwind", "direction": "up"}],
    "risk_flags": [],
}


async def test_analyze_parses_and_normalizes() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _openai_response(_MATERIAL)

    analyst = _analyst(handler)
    result = await analyst.analyze(
        _retrieval(_article("Nvidia capex", published=NOW - timedelta(minutes=30)))
    )

    assert isinstance(result, BriefingResult)
    assert result.has_material_update
    assert result.urgency == "notable"
    theme = result.themes[0]
    assert theme.direction == "bullish"  # synonym normalized
    assert theme.tickers == ["NVDA"]  # upper-cased
    assert result.watchlist_notes[0].direction == "bullish"
    # JSON mode requested.
    assert captured["body"]["response_format"] == {"type": "json_object"}


async def test_quiet_window_returns_no_material_update() -> None:
    quiet = {"has_material_update": False, "urgency": "routine", "headline": "", "themes": []}
    analyst = _analyst(lambda r: _openai_response(quiet))
    result = await analyst.analyze(_retrieval())
    assert result.has_material_update is False
    assert result.themes == []


async def test_invalid_json_raises_analyst_error() -> None:
    analyst = _analyst(lambda r: _openai_response("not json{"))
    with pytest.raises(AnalystError):
        await analyst.analyze(_retrieval(_article("x", published=NOW)))


async def test_http_error_raises_analyst_error() -> None:
    analyst = _analyst(lambda r: httpx.Response(500, json={"error": "boom"}))
    with pytest.raises(AnalystError):
        await analyst.analyze(_retrieval(_article("x", published=NOW)))


def test_user_message_marks_unverified_and_lists_prior_themes() -> None:
    retrieval = _retrieval(
        _article("Fresh item", published=NOW - timedelta(minutes=20)),
        _article("No date item", published=None),
    )
    msg = build_user_message(retrieval, prior_themes=["AI capex (strengthening)"])
    assert "Fresh item" in msg
    assert "UNVERIFIED" in msg  # the no-date item is flagged
    assert "AI capex (strengthening)" in msg


def test_user_message_caps_items() -> None:
    arts = [_article(f"item {i}", published=NOW - timedelta(minutes=i)) for i in range(10)]
    retrieval = _retrieval(*arts)
    msg = build_user_message(retrieval, max_items=3)
    assert "LATEST_NEWS (3 items)" in msg


def test_system_prompt_includes_watchlist_and_language() -> None:
    p = build_system_prompt(
        watchlist=["NVDA", "MU"], now=NOW, window_hours=16, language="Vietnamese"
    )
    assert "NVDA, MU" in p
    assert "Vietnamese" in p
