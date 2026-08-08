"""The shared LLM provider layer (committee plan Phase 2).

One class serves OpenAI and DeepSeek because DeepSeek's API is OpenAI-compatible.
These tests pin the behaviour the committee work depends on: identical requests
whoever answers, usage captured for cost comparison, and one repair attempt when
a model returns something unusable.
"""

import json

import httpx
import pytest
from pydantic import BaseModel

from app.config import Settings
from app.llm import (
    ChatProvider,
    ProviderError,
    available_providers,
    build_provider,
)


class Answer(BaseModel):
    verdict: str
    score: int


def _reply(content: str, *, usage: dict | None = None) -> dict:
    body: dict = {"choices": [{"message": {"content": content}}]}
    if usage is not None:
        body["usage"] = usage
    return body


def _provider(handler, *, name: str = "openai", model: str = "test-model") -> ChatProvider:
    return ChatProvider(
        name=name,
        api_key="k",
        base_url="https://api.example.com/v1",
        model=model,
        transport=httpx.MockTransport(handler),
    )


def _ok(content: str, usage: dict | None = None):
    return lambda request: httpx.Response(200, json=_reply(content, usage=usage))


# --- request shape ---------------------------------------------------------


async def test_sends_json_mode_and_both_messages() -> None:
    seen: dict = {}

    def handle(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_reply('{"verdict": "wait", "score": 1}'))

    await _provider(handle).complete_json(system="SYS", user="USR")

    assert seen["url"].endswith("/chat/completions")
    assert seen["auth"] == "Bearer k"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USR"},
    ]


async def test_deepseek_gets_the_identical_request() -> None:
    """Comparing two analysts is only fair if they were asked the same thing."""
    bodies: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=_reply('{"verdict": "wait", "score": 1}'))

    for name in ("openai", "deepseek"):
        await _provider(handle, name=name, model="m").complete_json(system="SYS", user="USR")

    assert bodies[0] == bodies[1]


async def test_max_tokens_is_only_sent_when_asked_for() -> None:
    seen: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=_reply("{}"))

    p = _provider(handle)
    await p.complete_json(system="s", user="u")
    await p.complete_json(system="s", user="u", max_tokens=64)

    assert "max_tokens" not in seen[0]
    assert seen[1]["max_tokens"] == 64


# --- usage capture ---------------------------------------------------------


async def test_captures_usage_and_identity() -> None:
    handler = _ok(
        '{"verdict": "wait", "score": 2}',
        usage={"prompt_tokens": 1200, "completion_tokens": 300},
    )
    result = await _provider(handler, name="deepseek", model="v4-flash").complete_json(
        system="s", user="u"
    )

    assert result.provider == "deepseek" and result.model == "v4-flash"
    assert result.usage.input_tokens == 1200
    assert result.usage.output_tokens == 300
    assert result.usage.latency_ms >= 0


async def test_accepts_the_responses_api_usage_names_too() -> None:
    handler = _ok("{}", usage={"input_tokens": 10, "output_tokens": 5})
    result = await _provider(handler).complete_json(system="s", user="u")
    assert result.usage.input_tokens == 10 and result.usage.output_tokens == 5


async def test_missing_usage_is_none_not_zero() -> None:
    """Zero would quietly understate cost in the provider comparison."""
    result = await _provider(_ok("{}")).complete_json(system="s", user="u")
    assert result.usage.input_tokens is None and result.usage.output_tokens is None


def test_usage_as_dict_shape() -> None:
    from app.llm import Usage

    assert Usage(1, 2, 30).as_dict() == {
        "inputTokens": 1,
        "outputTokens": 2,
        "latencyMs": 30,
    }


# --- validation and repair -------------------------------------------------


async def test_validates_into_the_schema() -> None:
    handler = _ok('{"verdict": "enter", "score": 7}')
    answer, result = await _provider(handler).complete_model(Answer, system="s", user="u")
    assert isinstance(answer, Answer) and answer.verdict == "enter" and answer.score == 7
    assert result.provider == "openai"


async def test_malformed_json_is_retried_once_then_succeeds() -> None:
    calls = {"n": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        body = "{oops" if calls["n"] == 1 else '{"verdict": "wait", "score": 1}'
        return httpx.Response(200, json=_reply(body))

    answer, _ = await _provider(handle).complete_model(Answer, system="s", user="u")
    assert calls["n"] == 2 and answer.verdict == "wait"


async def test_schema_violations_are_also_retried() -> None:
    """Valid JSON that misses a field is just as unusable as broken JSON."""
    calls = {"n": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        body = '{"verdict": "wait"}' if calls["n"] == 1 else '{"verdict": "wait", "score": 3}'
        return httpx.Response(200, json=_reply(body))

    answer, _ = await _provider(handle).complete_model(Answer, system="s", user="u")
    assert calls["n"] == 2 and answer.score == 3


async def test_gives_up_after_the_second_failure() -> None:
    """A model that won't comply twice won't comply a third time either."""
    calls = {"n": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_reply("not json at all"))

    with pytest.raises(ProviderError, match="failed validation"):
        await _provider(handle).complete_model(Answer, system="s", user="u")
    assert calls["n"] == 2


# --- failure handling ------------------------------------------------------


async def test_http_errors_become_provider_errors_naming_the_provider() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with pytest.raises(ProviderError, match="deepseek request failed"):
        await _provider(handle, name="deepseek").complete_json(system="s", user="u")


async def test_network_errors_are_wrapped() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(ProviderError):
        await _provider(handle).complete_json(system="s", user="u")


async def test_an_unexpected_body_shape_is_reported_clearly() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    with pytest.raises(ProviderError, match="unexpected shape"):
        await _provider(handle).complete_json(system="s", user="u")


def test_a_provider_without_a_key_refuses_to_construct() -> None:
    with pytest.raises(ProviderError, match="No API key"):
        ChatProvider(name="deepseek", api_key="", base_url="https://x", model="m")


# --- construction from settings --------------------------------------------


def test_build_provider_wires_each_provider_to_its_own_config() -> None:
    settings = Settings(
        _env_file=None,
        openai_api_key="oa",
        openai_base_url="https://api.openai.com/v1",
        prediction_model="gpt-4o-mini",
        deepseek_api_key="ds",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-v4-flash",
    )

    openai = build_provider("openai", settings)
    deepseek = build_provider("deepseek", settings)

    assert (openai.name, openai.model) == ("openai", "gpt-4o-mini")
    assert deepseek.base_url == "https://api.deepseek.com"
    assert deepseek.model == "deepseek-v4-flash"


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(ProviderError, match="Unknown provider"):
        build_provider("anthropic", Settings(_env_file=None))


def test_available_providers_reflects_which_keys_exist() -> None:
    """With one key configured the committee degrades to a single analyst."""
    both = Settings(_env_file=None, openai_api_key="a", deepseek_api_key="b")
    openai_only = Settings(_env_file=None, openai_api_key="a")
    neither = Settings(_env_file=None)

    assert available_providers(both) == ["openai", "deepseek"]
    assert available_providers(openai_only) == ["openai"]
    assert available_providers(neither) == []
