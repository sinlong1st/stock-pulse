"""Briefing step H: the model pulling live news itself via the web_search tool.

Web search only exists on the Responses API, so this is a second request path
rather than a flag on the existing one. The tests pin the parts that are easy to
get subtly wrong: which endpoint is called, that citations come from the API
envelope (not the model's JSON), and that the feeds-only path is untouched.
"""

import json

import httpx
import pytest

from app.briefing.analyst import (
    AnalystError,
    MarketAnalyst,
    _extract_responses_output,
    build_analyst,
    build_system_prompt,
    supports_web_search,
)
from app.briefing.render import render_briefing
from app.briefing.retrieval import RetrievalResult
from app.config import Settings
from datetime import UTC, datetime

RESULT_JSON = {
    "has_material_update": True,
    "urgency": "notable",
    "headline": "Chips wobble on China risk",
    "themes": [{"theme": "AI & semis", "direction": "bearish", "insight": "export curbs"}],
}


def _retrieval() -> RetrievalResult:
    return RetrievalResult(
        now=datetime(2026, 8, 6, 14, 0, tzinfo=UTC),
        window_hours=2.0,
        fresh=[],
        unverified=[],
        collected=0,
        stale_dropped=0,
    )


def _responses_body(text: str, citations: list[dict] | None = None) -> dict:
    return {
        "output": [
            {"type": "web_search_call", "status": "completed"},  # must be skipped
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": text,
                        "annotations": citations or [],
                    }
                ],
            },
        ]
    }


def _cite(url: str, title: str) -> dict:
    return {"type": "url_citation", "url": url, "title": title}


def _analyst(handler, **kw) -> MarketAnalyst:
    return MarketAnalyst(
        "k",
        watchlist=["NVDA"],
        transport=httpx.MockTransport(handler),
        **kw,
    )


# --- envelope parsing ------------------------------------------------------


def test_extracts_text_and_citations_skipping_tool_items() -> None:
    body = _responses_body(
        '{"ok": true}',
        [_cite("https://a.com/x", "A story"), _cite("https://b.com/y", "B story")],
    )
    text, sources = _extract_responses_output(body)
    assert text == '{"ok": true}'
    assert [s.url for s in sources] == ["https://a.com/x", "https://b.com/y"]
    assert sources[0].title == "A story"


def test_duplicate_citations_are_collapsed_keeping_order() -> None:
    body = _responses_body(
        "{}",
        [_cite("https://a.com", "A"), _cite("https://b.com", "B"), _cite("https://a.com", "A")],
    )
    _, sources = _extract_responses_output(body)
    assert [s.url for s in sources] == ["https://a.com", "https://b.com"]


def test_falls_back_to_output_text_when_no_message_item() -> None:
    text, sources = _extract_responses_output({"output": [], "output_text": '{"ok": 1}'})
    assert text == '{"ok": 1}' and sources == []


def test_empty_response_raises_rather_than_returning_nothing() -> None:
    with pytest.raises(AnalystError, match="no message text"):
        _extract_responses_output({"output": []})


# --- request shape ---------------------------------------------------------


async def test_web_search_uses_the_responses_endpoint_with_the_tool() -> None:
    seen: dict = {}

    def handle(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_responses_body(json.dumps(RESULT_JSON)))

    await _analyst(handle, web_search=True, model="gpt-4.1-mini").analyze(_retrieval())

    assert seen["url"].endswith("/responses")  # NOT /chat/completions
    assert seen["body"]["tools"] == [{"type": "web_search"}]
    # Must be a strict json_schema, never json_object: the live API rejects
    # web search + JSON mode ("Web Search cannot be used with JSON mode").
    fmt = seen["body"]["text"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["strict"] is True
    assert "sources" in fmt["schema"]["properties"]
    # System guidance about searching is only sent when the tool is attached.
    system = seen["body"]["input"][0]["content"]
    assert "web_search tool" in system


async def test_feeds_only_path_is_unchanged() -> None:
    seen: dict = {}

    def handle(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(RESULT_JSON)}}]},
        )

    result = await _analyst(handle).analyze(_retrieval())

    assert seen["url"].endswith("/chat/completions")
    assert "tools" not in seen["body"]
    assert "web_search tool" not in seen["body"]["messages"][0]["content"]
    assert result.sources == []  # nothing to cite without search


# --- results ---------------------------------------------------------------


async def test_envelope_annotations_win_over_the_models_own_list() -> None:
    """Annotations are provably fetched, so they beat what the model claims."""
    claimed = {**RESULT_JSON, "sources": [{"url": "https://made-up.example", "title": "Fake"}]}

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_responses_body(
                json.dumps(claimed), [_cite("https://real.com/a", "Real story")]
            ),
        )

    result = await _analyst(handle, web_search=True).analyze(_retrieval())

    assert [s.url for s in result.sources] == ["https://real.com/a"]
    assert result.headline == "Chips wobble on China risk"  # rest still parsed


async def test_falls_back_to_model_reported_sources_when_no_annotations() -> None:
    """The usual case: OpenAI emits url_citations for prose, and ours is JSON."""
    reported = {
        **RESULT_JSON,
        "sources": [
            {"url": "https://reuters.com/a", "title": "Reuters piece"},
            {"url": "not-a-url", "title": "junk"},  # dropped
            {"url": "https://reuters.com/a", "title": "dupe"},  # collapsed
        ],
    }

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_responses_body(json.dumps(reported)))

    result = await _analyst(handle, web_search=True).analyze(_retrieval())
    assert [s.url for s in result.sources] == ["https://reuters.com/a"]


async def test_malformed_json_is_retried_once() -> None:
    """Observed live: strict schema still returns bad JSON now and then, and a
    scheduled briefing shouldn't be lost to it."""
    calls = {"n": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        body = '{"broken": ' if calls["n"] == 1 else json.dumps(RESULT_JSON)
        return httpx.Response(200, json=_responses_body(body))

    result = await _analyst(handle, web_search=True).analyze(_retrieval())
    assert calls["n"] == 2
    assert result.headline == "Chips wobble on China risk"


async def test_two_bad_responses_give_up() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_responses_body("{nope"))

    with pytest.raises(AnalystError, match="valid JSON"):
        await _analyst(handle, web_search=True).analyze(_retrieval())


async def test_a_web_search_http_failure_is_an_analyst_error() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="nope")

    with pytest.raises(AnalystError, match="web-search request failed"):
        await _analyst(handle, web_search=True).analyze(_retrieval())


# --- model guardrail -------------------------------------------------------


@pytest.mark.parametrize(
    "model,ok",
    [
        ("gpt-4.1-mini", True),
        ("gpt-4.1", True),
        ("gpt-5.6", True),
        ("gpt-4o-mini", False),  # the current default cannot search
        ("gpt-4o", False),
        ("", False),
    ],
)
def test_supports_web_search(model, ok) -> None:
    assert supports_web_search(model) is ok


def test_build_analyst_warns_but_still_builds_on_an_unknown_model(caplog) -> None:
    """OpenAI adds models faster than our list; warn, don't block a briefing."""
    settings = Settings(
        _env_file=None,
        openai_api_key="k",
        briefing_web_search_enabled=True,
        briefing_model="gpt-4o-mini",
    )
    with caplog.at_level("WARNING"):
        analyst = build_analyst(settings)
    assert analyst.web_search is True
    assert "not a known web-search model" in caplog.text


def test_build_analyst_is_quiet_with_a_capable_model(caplog) -> None:
    settings = Settings(
        _env_file=None,
        openai_api_key="k",
        briefing_web_search_enabled=True,
        briefing_model="gpt-4.1-mini",
    )
    with caplog.at_level("WARNING"):
        build_analyst(settings)
    assert "not a known web-search model" not in caplog.text


# --- rendering -------------------------------------------------------------


def test_sources_render_as_clickable_citations() -> None:
    from app.briefing.models import BriefingResult, WebSource

    result = BriefingResult(
        has_material_update=True,
        headline="Chips wobble",
        sources=[
            WebSource(url="https://a.com/x", title="A story"),
            WebSource(url="https://b.com/y", title=""),
        ],
    )
    text = render_briefing(result, language="English")

    assert "Sources:" in text
    assert "A story — https://a.com/x" in text
    assert "https://b.com/y" in text  # falls back to the bare URL with no title


def test_no_sources_block_without_web_search() -> None:
    from app.briefing.models import BriefingResult

    text = render_briefing(
        BriefingResult(has_material_update=True, headline="Quiet"), language="English"
    )
    assert "Sources:" not in text


def test_sources_are_capped() -> None:
    from app.briefing.models import BriefingResult, WebSource

    result = BriefingResult(
        has_material_update=True,
        headline="Busy day",
        sources=[WebSource(url=f"https://s{i}.com", title=f"S{i}") for i in range(12)],
    )
    text = render_briefing(result, language="English")
    assert text.count("https://s") == 5


def test_system_prompt_only_mentions_search_when_enabled() -> None:
    kw = dict(
        watchlist=["NVDA"],
        now=datetime(2026, 8, 6, tzinfo=UTC),
        window_hours=2.0,
        language="English",
    )
    assert "web_search tool" in build_system_prompt(**kw, web_search=True)
    assert "web_search tool" not in build_system_prompt(**kw)
