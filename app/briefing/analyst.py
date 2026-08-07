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

from app.briefing.models import BriefingResult, WebSource
from app.briefing.retrieval import RetrievalResult, RetrievedItem
from app.config import Settings, get_settings
from app.prefs import resolve_language
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
5. PRICE ACTION - PRICE_MOVES lists notable market moves in the watchlist today. \
If a stock moved notably but has NO news here explaining it, still surface it as a \
short watchlist_note labeled price-driven (e.g. "down 10% today, no clear \
catalyst"). Never invent a reason for the move.

Rules:
  - Ground every claim in a provided headline. Never speculate beyond the news.
  - No investment advice, no price targets - analysis, not recommendations.
  - Be concise and skimmable; a tired human reads this on a phone.
  - "theme" is a short natural label (e.g. "AI & semiconductors", "Fed & rates"), \
NOT the raw focus-theme list.
  - "risk_flags" lists only ACTUAL geopolitical/war/oil/macro risks live right \
now, each a short phrase; use [] when there are none. NEVER copy the schema's \
description text into the output.
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
  "risk_flags": []
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


# Only added when the web_search tool is actually attached. The base prompt says
# the model "may" use search; with the tool present it needs firmer direction,
# plus the freshness rules restated — a searched page is as recap-prone as a feed.
_WEB_SEARCH_BLOCK = """

WEB SEARCH: you have a web_search tool. You MUST run at least one search before
answering — always, on every briefing. Use it to (a) confirm the headlines above
are real and current, and (b) find anything material our feeds missed for the
watchlist.

An EMPTY or thin LATEST_NEWS list does NOT mean nothing happened — it means our
collectors found nothing, which is exactly when searching matters most. Never
report "no material update" without having searched first.

Search a few targeted queries (the watchlist names, plus the market backdrop),
not many broad ones. Everything you find is subject to the SAME freshness rules:
judge the EVENT time, not the publish date, and treat roundups as background.
Prefer primary sources and major outlets.

Then list every page you actually opened in the "sources" array, each with its
real URL and page title. These are shown to the user as citations, so they must
be pages you genuinely retrieved with the tool — never invent or guess a URL, and
never list one you did not open. If you did not search, leave "sources" empty."""


def build_system_prompt(
    *,
    watchlist: list[str],
    now: datetime,
    window_hours: float,
    language: str,
    focus: str | None = None,
    web_search: bool = False,
) -> str:
    prompt = _SYSTEM_PROMPT.format(
        watchlist=", ".join(watchlist) if watchlist else "(none configured)",
        now=now.isoformat(timespec="minutes"),
        window_hours=window_hours,
        language=language or "English",
    )
    if web_search:
        prompt += _WEB_SEARCH_BLOCK
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
    price_moves: str | None = None,
) -> str:
    items = retrieval.usable[:max_items]
    if items:
        news_block = "\n".join(_format_item(i) for i in items)
    else:
        news_block = "(no fresh news in this window)"

    prior = prior_themes or []
    prior_block = "\n".join(f"- {t}" for t in prior) if prior else "(none)"

    focus_line = f"FOCUS REQUEST: {focus}\n" if focus else ""
    moves_line = f"PRICE_MOVES (today): {price_moves}\n" if price_moves else ""
    return (
        f"{focus_line}"
        f"NOW: {retrieval.now.isoformat(timespec='minutes')}\n"
        f"FRESHNESS WINDOW: {retrieval.window_hours:.0f}h\n"
        f"{moves_line}\n"
        f"LATEST_NEWS ({len(items)} items):\n{news_block}\n\n"
        f"PRIOR_THEMES (last few hours):\n{prior_block}"
    )


_DIRECTIONS = ["bullish", "bearish", "mixed"]

# Strict Structured Outputs: every property must be listed in `required`, and
# `additionalProperties` must be false at every level. Optional values are
# expressed as a null union rather than by omission.
_BRIEFING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "has_material_update",
        "urgency",
        "headline",
        "themes",
        "watchlist_notes",
        "risk_flags",
        "sources",
    ],
    "properties": {
        "has_material_update": {"type": "boolean"},
        "urgency": {"type": "string", "enum": ["routine", "notable", "urgent"]},
        "headline": {"type": "string"},
        "themes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "theme",
                    "direction",
                    "tickers",
                    "insight",
                    "trend",
                    "freshness",
                    "event_time",
                ],
                "properties": {
                    "theme": {"type": "string"},
                    "direction": {"type": "string", "enum": _DIRECTIONS},
                    "tickers": {"type": "array", "items": {"type": "string"}},
                    "insight": {"type": "string"},
                    "trend": {
                        "type": "string",
                        "enum": ["new", "strengthening", "fading", "reversing"],
                    },
                    "freshness": {"type": "string", "enum": ["new", "background"]},
                    "event_time": {"type": ["string", "null"]},
                },
            },
        },
        "watchlist_notes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["ticker", "note", "direction"],
                "properties": {
                    "ticker": {"type": "string"},
                    "note": {"type": "string"},
                    "direction": {"type": "string", "enum": _DIRECTIONS},
                },
            },
        },
        "risk_flags": {"type": "array", "items": {"type": "string"}},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["url", "title"],
                "properties": {"url": {"type": "string"}, "title": {"type": "string"}},
            },
        },
    },
}


def _clean_sources(raw: object) -> list[WebSource]:
    """Keep only plausible http(s) URLs, de-duplicated, order preserved."""
    out: dict[str, WebSource] = {}
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url.startswith(("http://", "https://")) or url in out:
            continue
        out[url] = WebSource(url=url, title=str(item.get("title") or "").strip())
    return list(out.values())


def _extract_responses_output(data: dict) -> tuple[str, list[WebSource]]:
    """Pull the assistant text and its url citations out of a /responses body.

    The Responses API returns a list of output items — web_search_call entries
    alongside the message — so we walk it rather than indexing a fixed position.
    `output_text` is a convenience field the API may also provide; it is used as
    a fallback when the walk finds nothing.
    """
    chunks: list[str] = []
    sources: dict[str, WebSource] = {}  # url -> source, de-duped, order kept

    for item in data.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if not isinstance(part, dict):
                continue
            if isinstance(part.get("text"), str):
                chunks.append(part["text"])
            for note in part.get("annotations") or []:
                if not isinstance(note, dict) or note.get("type") != "url_citation":
                    continue
                url = str(note.get("url") or "").strip()
                if url and url not in sources:
                    sources[url] = WebSource(url=url, title=str(note.get("title") or "").strip())

    text = "".join(chunks).strip() or str(data.get("output_text") or "").strip()
    if not text:
        raise AnalystError("OpenAI web-search response contained no message text.")
    return text, list(sources.values())


class MarketAnalyst:
    """Briefing analyst backed by OpenAI.

    Two request paths, because web search is only available on the newer API:

    - **feeds only** (default) — `/chat/completions` with JSON mode. Cheap,
      deterministic, and works with small models like `gpt-4o-mini`.
    - **web search on** — `/responses` with the `web_search` tool, so the model
      can pull and cross-check live coverage beyond our RSS feeds. Costs more,
      is less repeatable, and needs a search-capable model.

    Either way the model's JSON is validated into `BriefingResult`; the web path
    additionally attaches the URLs it actually read as `sources`.
    """

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
        web_search: bool = False,
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
        self.web_search = web_search
        self._transport = transport

    async def analyze(
        self,
        retrieval: RetrievalResult,
        *,
        prior_themes: list[str] | None = None,
        focus: str | None = None,
        price_moves: str | None = None,
    ) -> BriefingResult:
        system = build_system_prompt(
            watchlist=self.watchlist,
            now=retrieval.now,
            window_hours=retrieval.window_hours,
            language=self.language,
            focus=focus,
            web_search=self.web_search,
        )
        user = build_user_message(
            retrieval,
            prior_themes=prior_themes,
            max_items=self.max_items,
            focus=focus,
            price_moves=price_moves,
        )
        if self.web_search:
            # Strict Structured Outputs should always be valid JSON, but in
            # testing roughly one call in five came back malformed. A scheduled
            # briefing shouldn't be lost to that, so retry once.
            for attempt in (1, 2):
                content, annotated = await self._analyze_with_web_search(system, user)
                try:
                    result = self._parse(content)
                    break
                except AnalystError:
                    if attempt == 2:
                        raise
                    logger.warning("Web-search briefing returned bad JSON; retrying once.")
            # Prefer citations from the API envelope when present — those are
            # pages the tool provably fetched. In practice OpenAI only emits
            # them for prose answers, and ours is JSON, so we normally fall back
            # to the source list the model reports inside its own output.
            try:
                reported = _clean_sources(json.loads(content).get("sources"))
            except (json.JSONDecodeError, AttributeError):
                reported = []
            return result.model_copy(update={"sources": annotated or reported})

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

    async def _analyze_with_web_search(
        self, system: str, user: str
    ) -> tuple[str, list[WebSource]]:
        """Call /responses with the web_search tool, returning (json, sources)."""
        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "tools": [{"type": "web_search"}],
            # Structured Outputs, NOT JSON mode: the API rejects web search with
            # `json_object` ("Web Search cannot be used with JSON mode"), but a
            # strict json_schema is accepted and also guarantees the shape.
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "market_briefing",
                    "schema": _BRIEFING_SCHEMA,
                    "strict": True,
                }
            },
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self.base_url}/responses",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise AnalystError(f"OpenAI web-search request failed: {exc}") from exc
        return _extract_responses_output(data)

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


# Models known to support the web_search tool on /responses. Used only to warn —
# OpenAI's list moves, so an unknown model is allowed through rather than blocked.
WEB_SEARCH_MODELS = ("gpt-4.1", "gpt-4.1-mini", "gpt-5")


def supports_web_search(model: str) -> bool:
    name = (model or "").strip().lower()
    return any(name.startswith(prefix) for prefix in WEB_SEARCH_MODELS)


def build_analyst(settings: Settings | None = None) -> MarketAnalyst:
    """Construct the configured analyst. Raises if no API key is set."""
    settings = settings or get_settings()
    if settings.briefing_web_search_enabled and not supports_web_search(settings.briefing_model):
        # Not fatal: OpenAI adds models faster than this list is updated, and a
        # wrong guess here shouldn't block a briefing. The API will reject it if
        # it truly can't search, and that surfaces as a normal AnalystError.
        logger.warning(
            "BRIEFING_WEB_SEARCH_ENABLED is on but BRIEFING_MODEL=%r is not a known "
            "web-search model. Try one of: %s.",
            settings.briefing_model,
            ", ".join(WEB_SEARCH_MODELS),
        )
    return MarketAnalyst(
        settings.openai_api_key,
        model=settings.briefing_model,
        base_url=settings.openai_base_url,
        language=resolve_language(settings),
        max_items=settings.briefing_max_items,
        web_search=settings.briefing_web_search_enabled,
    )
