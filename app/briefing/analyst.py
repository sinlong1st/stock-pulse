"""The briefing analyst (Step B): synthesize fresh news into a market read.

Takes a `RetrievalResult` (the freshly fetched, windowed news) plus recent
prior themes for trend continuity, asks the model to act as a market
secretary, and validates the JSON into a `BriefingResult`. Web search (the
model pulling news itself) is a later step; here it reasons only over the news
we hand it, so it stays cheap and deterministic.
"""

import json
import logging
from datetime import datetime

import httpx
from pydantic import ValidationError

from app.briefing.models import BriefingResult
from app.briefing.retrieval import RetrievalResult, RetrievedItem
from app.config import Settings, get_settings
from app.watchlist import get_watchlist_config

logger = logging.getLogger("stockpulse.briefing.analyst")


class AnalystError(Exception):
    """Raised when the briefing analysis fails (API error or invalid output)."""


_SYSTEM_PROMPT = """\
You are StockPulse, a sharp market-intelligence analyst acting as a personal \
secretary for one investor. Your ONLY job: from the latest news provided, \
surface what could move THIS investor's watchlist — and be honest when nothing \
material has changed.

WATCHLIST: {watchlist}
FOCUS THEMES: AI & semiconductors, big tech, macro/Fed/rates/inflation, \
geopolitics & war, energy/oil, supply chains.
NOW: {now}    FRESHNESS WINDOW: {window_hours:.0f}h

You are given:
  - LATEST_NEWS: freshly fetched headlines (source, publish time, snippet). Some \
are marked UNVERIFIED (no reliable publish time) or [likely RECAP/roundup] — \
treat those with caution and never lead with them.
  - PRIOR_THEMES: what you flagged in the last few hours, for trend continuity.

For EACH item, FIRST judge its recency, because a recent PUBLISH time is not \
proof of recent NEWS:
  - temporal_type: breaking | developing | recap_or_roundup | evergreen_analysis
  - event_time: when the underlying EVENT happened (from the text), NOT the \
publish time. Weekly/monthly summaries and "week in review" pieces describe OLD \
events even when freshly published; items hinted [likely RECAP/roundup] are \
usually these.
Freshness rules:
  - Treat an item as NEW only if the underlying EVENT is within the freshness \
window of NOW — not merely because its publish time is recent.
  - recap_or_roundup and evergreen_analysis are NEVER "new": you may cite them as \
background/trend context (freshness="background"), never as this-window developments.
  - If an item's real event time is unclear, downgrade its weight — do not assume \
it is fresh.

Analyze:
1. RELEVANCE - drop noise, celebrity, sports, generic listicles. Keep only what \
plausibly affects the watchlist or the focus themes.
2. IMPACT - for each kept item: which ticker(s)/theme, direction (bullish / \
bearish / mixed), and WHY in one clause. Separate a real catalyst from routine chatter.
3. TREND - versus PRIOR_THEMES: is a storyline new, strengthening, fading, or \
reversing? Trends matter more than one-off headlines.
4. MATERIALITY - set has_material_update=false if this window brings nothing a \
busy investor needs. Repetition of an already-reported story is NOT material \
unless it escalated. Do not invent significance.

Rules:
  - Ground every claim in a provided headline. Never speculate beyond the news.
  - No investment advice, no price targets - analysis, not recommendations.
  - Be concise and skimmable; a tired human reads this on a phone.
  - Write all human-facing text (headline, insight, note, risk_flags) in {language}. \
Keep JSON keys, enum values, and tickers exactly as specified in English.

Return JSON ONLY with this shape:
{{
  "has_material_update": true|false,
  "urgency": "routine"|"notable"|"urgent",
  "headline": "one-line gist, or empty string if nothing material",
  "themes": [
    {{"theme": "...", "direction": "bullish|bearish|mixed", "tickers": ["..."],
      "insight": "1-2 sentences with the why", "trend": "new|strengthening|fading|reversing",
      "freshness": "new|background", "event_time": "when the event happened, or null",
      "sources": ["source name(s)"]}}
  ],
  "watchlist_notes": [{{"ticker": "...", "note": "...", "direction": "bullish|bearish|mixed"}}],
  "risk_flags": ["war/geopolitics/oil shocks worth watching, if any"]
}}"""


_FOCUS_BLOCK = """

FOCUS MODE — the user asked specifically about: {focus}
Interpret it with common sense: fix obvious typos and map names to tickers
(e.g. "micosoft" -> Microsoft (MSFT), "wdcc" -> Western Digital (WDC), "spacex"
-> SpaceX). Report ONLY on that one company/stock: the latest news and what it
means for it — ignore unrelated market news. Name the company you settled on in
the headline so the user can confirm you understood. If you genuinely cannot
tell what company they mean, say so in the headline and set
has_material_update=false."""


def build_system_prompt(
    *,
    watchlist: list[str],
    now: datetime,
    window_hours: float,
    language: str,
    focus: str | None = None,
) -> str:
    prompt = _SYSTEM_PROMPT.format(
        watchlist=", ".join(watchlist) if watchlist else "(none configured)",
        now=now.isoformat(timespec="minutes"),
        window_hours=window_hours,
        language=language or "English",
    )
    if focus:
        prompt += _FOCUS_BLOCK.format(focus=focus)
    return prompt


def _format_item(item: RetrievedItem) -> str:
    if item.timestamp_verified and item.published_at is not None:
        when = item.published_at.isoformat(timespec="minutes")
        age = f", {item.age_hours:.1f}h ago" if item.age_hours is not None else ""
        stamp = f"published {when}{age}"
    else:
        stamp = "publish time UNKNOWN (UNVERIFIED — do not assume fresh)"
    recap = " [likely RECAP/roundup]" if item.likely_recap else ""
    snippet = (item.summary or "").strip()
    snippet = f" :: {snippet}" if snippet else ""
    return f"- [{item.source}] {item.title} ({stamp}){recap}{snippet}"


def build_user_message(
    retrieval: RetrievalResult,
    *,
    prior_themes: list[str] | None = None,
    max_items: int = 40,
    focus: str | None = None,
) -> str:
    items = retrieval.usable[:max_items]
    if items:
        news_block = "\n".join(_format_item(i) for i in items)
    else:
        news_block = "(no fresh news in this window)"

    prior = prior_themes or []
    prior_block = "\n".join(f"- {t}" for t in prior) if prior else "(none)"

    focus_line = f"FOCUS REQUEST: {focus}\n" if focus else ""
    return (
        f"{focus_line}"
        f"NOW: {retrieval.now.isoformat(timespec='minutes')}\n"
        f"FRESHNESS WINDOW: {retrieval.window_hours:.0f}h\n\n"
        f"LATEST_NEWS ({len(items)} items):\n{news_block}\n\n"
        f"PRIOR_THEMES (last few hours):\n{prior_block}"
    )


class MarketAnalyst:
    """Briefing analyst backed by the OpenAI chat completions API."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        watchlist: list[str] | None = None,
        language: str = "English",
        max_items: int = 40,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise AnalystError("OPENAI_API_KEY is not set.")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.watchlist = (
            watchlist if watchlist is not None else list(get_watchlist_config().tickers)
        )
        self.language = language
        self.max_items = max_items
        self.timeout = timeout
        self._transport = transport

    async def analyze(
        self,
        retrieval: RetrievalResult,
        *,
        prior_themes: list[str] | None = None,
        focus: str | None = None,
    ) -> BriefingResult:
        system = build_system_prompt(
            watchlist=self.watchlist,
            now=retrieval.now,
            window_hours=retrieval.window_hours,
            language=self.language,
            focus=focus,
        )
        user = build_user_message(
            retrieval, prior_themes=prior_themes, max_items=self.max_items, focus=focus
        )
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        content = await self._request(payload)
        return self._parse(content)

    async def _request(self, payload: dict) -> str:
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise AnalystError(f"OpenAI request failed: {exc}") from exc

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AnalystError(f"Unexpected OpenAI response shape: {exc}") from exc

    @staticmethod
    def _parse(content: str) -> BriefingResult:
        try:
            raw = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AnalystError(f"AI did not return valid JSON: {exc}") from exc
        try:
            return BriefingResult.model_validate(raw)
        except ValidationError as exc:
            raise AnalystError(f"AI output failed validation: {exc}") from exc


def build_analyst(settings: Settings | None = None) -> MarketAnalyst:
    """Construct the configured analyst. Raises if no API key is set."""
    settings = settings or get_settings()
    return MarketAnalyst(
        settings.openai_api_key,
        model=settings.briefing_model,
        base_url=settings.openai_base_url,
        language=settings.output_language,
        max_items=settings.briefing_max_items,
    )
