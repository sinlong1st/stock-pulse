"""Resolving what the user typed to a ticker.

Three layers, each covering the previous one's blind spot: exact Yahoo search,
Yahoo fuzzy search behind a similarity gate, then an AI guess that is verified
against real data. The gate matters most — naming the wrong company is worse
than saying "not found".
"""

import json

import httpx
import pytest

from app.commands.symbols import _is_primary, _similarity, resolve_symbol, resolve_symbol_smart
from app.config import Settings


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, openai_api_key="k", **kw)


def _quotes(*rows: tuple[str, str]) -> dict:
    return {
        "quotes": [
            {"symbol": s, "shortname": n, "quoteType": "EQUITY"} for s, n in rows
        ]
    }


def _yahoo(exact: dict | None = None, fuzzy: dict | None = None):
    """Mock transport answering the two search modes differently."""

    def handle(request: httpx.Request) -> httpx.Response:
        is_fuzzy = request.url.params.get("enableFuzzyQuery") == "true"
        body = (fuzzy if is_fuzzy else exact) or {"quotes": []}
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handle)


# --- similarity + listing preference ---------------------------------------


def test_similarity_scores_typos_high_and_different_companies_low() -> None:
    assert _similarity("teslaa", "TSLA", "Tesla, Inc.") > 0.85
    assert _similarity("micosoft", "MSFT", "Microsoft Corporation") > 0.85
    # The real trap: Yahoo offers ROCKETBOOT for "rocketlab".
    assert _similarity("rocketlab", "ROC.AX", "ROCKETBOOT FPO [ROC]") < 0.80


def test_primary_listing_detection() -> None:
    assert _is_primary("MSFT") and _is_primary("RKLB")
    # Foreign / derivative listings carry an exchange suffix.
    assert not _is_primary("MSFT34.SA")
    assert not _is_primary("MSFT.NE")
    assert not _is_primary("TL0.F")


# --- exact search ----------------------------------------------------------


async def test_exact_match_prefers_the_us_listing() -> None:
    transport = _yahoo(exact=_quotes(("MSFT34.SA", "MICROSOFT DRN"), ("MSFT", "Microsoft")))
    assert await resolve_symbol("microsoft", settings=_settings(), transport=transport) == (
        "MSFT",
        "Microsoft",
    )


async def test_falls_back_to_top_hit_when_none_are_primary() -> None:
    transport = _yahoo(exact=_quotes(("ROC.AX", "Rocketboot")))
    got = await resolve_symbol("rocketboot", settings=_settings(), transport=transport)
    assert got == ("ROC.AX", "Rocketboot")


# --- fuzzy search + the gate -----------------------------------------------


async def test_fuzzy_rescues_a_typo() -> None:
    transport = _yahoo(exact={"quotes": []}, fuzzy=_quotes(("TSLA", "Tesla, Inc.")))
    assert await resolve_symbol("teslaa", settings=_settings(), transport=transport) == (
        "TSLA",
        "Tesla, Inc.",
    )


async def test_fuzzy_picks_the_us_listing_over_an_equally_similar_foreign_one() -> None:
    """Regression: 'micosoft' landed on MSFT34.SA because the names tie."""
    transport = _yahoo(
        exact={"quotes": []},
        fuzzy=_quotes(
            ("MSFT.NE", "MICROSOFT CDR (CAD HEDGED)"),
            ("MSFT34.SA", "MICROSOFT   DRN"),
            ("MSFT", "Microsoft Corporation"),
        ),
    )
    got = await resolve_symbol("micosoft", settings=_settings(), transport=transport)
    assert got == ("MSFT", "Microsoft Corporation")


async def test_a_merely_similar_company_is_rejected() -> None:
    """'rocketlab' must NOT resolve to ROCKETBOOT — wrong is worse than none."""
    transport = _yahoo(exact={"quotes": []}, fuzzy=_quotes(("ROC.AX", "ROCKETBOOT FPO [ROC]")))
    assert await resolve_symbol("rocketlab", settings=_settings(), transport=transport) is None


async def test_nothing_at_all_returns_none() -> None:
    transport = _yahoo()
    assert await resolve_symbol("asdfqwerzz", settings=_settings(), transport=transport) is None


# --- AI fallback -----------------------------------------------------------


def _with_ai(reply: str, *, exact_for: dict[str, dict] | None = None):
    """Transport that answers OpenAI with `reply` and Yahoo per `exact_for`."""
    exact_for = exact_for or {}

    def handle(request: httpx.Request) -> httpx.Response:
        if "openai" in request.url.host or request.url.path.endswith("/chat/completions"):
            return httpx.Response(200, json={"choices": [{"message": {"content": reply}}]})
        q = request.url.params.get("q", "")
        return httpx.Response(200, json=exact_for.get(q, {"quotes": []}))

    return httpx.MockTransport(handle)


async def test_ai_resolves_run_together_words_and_is_verified() -> None:
    """Yahoo finds 'rocket lab' but not 'rocketlab'; the model bridges the gap."""
    transport = _with_ai("RKLB", exact_for={"RKLB": _quotes(("RKLB", "Rocket Lab Corporation"))})
    got = await resolve_symbol_smart("rocketlab", settings=_settings(), transport=transport)
    assert got == ("RKLB", "Rocket Lab Corporation")


async def test_the_query_reaches_the_model_in_lower_case() -> None:
    """Regression: the app uppercases the search box, and an ALL-CAPS typo reads
    to the model as an unknown ticker — 'ROCKETLUB' returned NONE in production
    where 'rocketlub' returns RKLB."""
    seen: dict = {}

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            seen["user"] = json.loads(request.content)["messages"][-1]["content"]
            return httpx.Response(200, json={"choices": [{"message": {"content": "RKLB"}}]})
        q = request.url.params.get("q", "")
        body = _quotes(("RKLB", "Rocket Lab")) if q == "RKLB" else {"quotes": []}
        return httpx.Response(200, json=body)

    got = await resolve_symbol_smart(
        "ROCKETLUB", settings=_settings(), transport=httpx.MockTransport(handle)
    )
    assert seen["user"] == "rocketlub"
    assert got == ("RKLB", "Rocket Lab")


async def test_a_hallucinated_ticker_is_rejected() -> None:
    """The model's guess must exist; ZZZZ resolves to nothing, so we give up."""
    transport = _with_ai("ZZZZ")  # no Yahoo hit for it
    assert await resolve_symbol_smart("nonsense", settings=_settings(), transport=transport) is None


async def test_ai_saying_none_is_respected() -> None:
    transport = _with_ai("NONE")
    assert await resolve_symbol_smart("asdfqwerzz", settings=_settings(), transport=transport) is None


@pytest.mark.parametrize("reply", ["I think it's RKLB", "rklb!!", "", "   ", "NOT A TICKER"])
async def test_junk_ai_replies_are_rejected(reply) -> None:
    transport = _with_ai(reply, exact_for={"RKLB": _quotes(("RKLB", "Rocket Lab"))})
    got = await resolve_symbol_smart("rocketlab", settings=_settings(), transport=transport)
    assert got is None


async def test_no_ai_call_when_search_already_worked() -> None:
    """The fallback costs a request — it must only run when needed."""
    calls = {"openai": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            calls["openai"] += 1
            return httpx.Response(200, json={"choices": [{"message": {"content": "X"}}]})
        return httpx.Response(200, json=_quotes(("RKLB", "Rocket Lab")))

    got = await resolve_symbol_smart(
        "rocket lab", settings=_settings(), transport=httpx.MockTransport(handle)
    )
    assert got == ("RKLB", "Rocket Lab")
    assert calls["openai"] == 0


async def test_without_an_api_key_it_just_gives_up() -> None:
    transport = _yahoo()
    settings = Settings(_env_file=None, openai_api_key="")
    assert await resolve_symbol_smart("rocketlab", settings=settings, transport=transport) is None


async def test_search_errors_are_not_fatal() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    got = await resolve_symbol("tesla", settings=_settings(), transport=httpx.MockTransport(handle))
    assert got is None
