"""One interface over the chat LLMs this project talks to.

Committee plan Phase 2. The point is that a caller can ask for a validated
structured answer without caring which provider produced it, so the same
prediction prompt can run through OpenAI and DeepSeek and be compared fairly.

**Both providers use the same class.** DeepSeek's API is OpenAI-compatible —
same `/chat/completions` path, same request shape, same `Authorization: Bearer`
header — so the only differences are the base URL, key and model name. A second
implementation would be duplicated code pretending to be an abstraction.

What this adds over a raw httpx call:

- **Validation with one repair attempt.** Models occasionally emit malformed JSON
  even in JSON mode; a single retry costs far less than losing the analysis.
- **Token usage and latency**, so "what did this cost" is answerable from data.
  Phase 3 compares providers, and that comparison needs cost as well as accuracy.
- **A named identity** (`openai`, `deepseek`) recorded alongside every result.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings

logger = logging.getLogger("stockpulse.llm")

T = TypeVar("T", bound=BaseModel)


class ProviderError(Exception):
    """A provider could not produce a usable answer."""


@dataclass(frozen=True)
class Usage:
    """What one call consumed. None when the provider didn't report it."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int = 0

    def as_dict(self) -> dict:
        return {
            "inputTokens": self.input_tokens,
            "outputTokens": self.output_tokens,
            "latencyMs": self.latency_ms,
        }


@dataclass(frozen=True)
class LLMResult:
    """A validated answer plus what it cost to get it."""

    content: str
    provider: str
    model: str
    usage: Usage


def _usage_from(payload: dict, latency_ms: int) -> Usage:
    """Read token counts. Chat Completions says prompt/completion; the Responses
    API says input/output. Accept either rather than depending on one shape."""
    raw = payload.get("usage") or {}

    def pick(*names: str) -> int | None:
        for name in names:
            value = raw.get(name)
            if isinstance(value, int):
                return value
        return None

    return Usage(
        input_tokens=pick("prompt_tokens", "input_tokens"),
        output_tokens=pick("completion_tokens", "output_tokens"),
        latency_ms=latency_ms,
    )


class ChatProvider:
    """An OpenAI-compatible chat endpoint. Serves OpenAI and DeepSeek alike."""

    def __init__(
        self,
        *,
        name: str,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ProviderError(f"No API key configured for {name}.")
        self.name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._transport = transport

    async def _post(self, payload: dict) -> tuple[str, Usage]:
        started = time.monotonic()
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
            raise ProviderError(f"{self.name} request failed: {exc}") from exc

        latency_ms = int((time.monotonic() - started) * 1000)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.name} returned an unexpected shape: {exc}") from exc
        return content or "", _usage_from(data, latency_ms)

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResult:
        """One JSON-mode call. Returns raw text; the caller validates."""
        payload: dict = {
            "model": self.model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        content, usage = await self._post(payload)
        return LLMResult(content=content, provider=self.name, model=self.model, usage=usage)

    async def complete_model(
        self,
        schema: type[T],
        *,
        system: str,
        user: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> tuple[T, LLMResult]:
        """A validated answer, retrying once if the first is unusable.

        JSON mode is not a guarantee — malformed output happens, and so does
        valid JSON that misses a required field. One repair attempt is far
        cheaper than dropping the analysis, but a second would just burn tokens
        on a model that clearly isn't going to comply.
        """
        last_error: Exception | None = None
        for attempt in (1, 2):
            result = await self.complete_json(
                system=system, user=user, temperature=temperature, max_tokens=max_tokens
            )
            try:
                return schema.model_validate(json.loads(result.content)), result
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                if attempt == 1:
                    logger.warning(
                        "%s returned unusable output (%s); retrying once.",
                        self.name,
                        type(exc).__name__,
                    )
        raise ProviderError(f"{self.name} output failed validation: {last_error}")


def build_provider(
    name: str, settings: Settings | None = None, *, transport: httpx.BaseTransport | None = None
) -> ChatProvider:
    """Construct a provider by name. Raises ProviderError if it isn't configured."""
    settings = settings or get_settings()
    if name == "openai":
        return ChatProvider(
            name="openai",
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.prediction_model,
            transport=transport,
        )
    if name == "deepseek":
        return ChatProvider(
            name="deepseek",
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            transport=transport,
        )
    raise ProviderError(f"Unknown provider {name!r}.")


def available_providers(settings: Settings | None = None) -> list[str]:
    """Providers that actually have a key, in a stable order.

    Used by the second-opinion path: with only one key configured the feature
    degrades to a single analyst rather than failing.
    """
    settings = settings or get_settings()
    out = []
    if settings.openai_api_key:
        out.append("openai")
    if settings.deepseek_api_key:
        out.append("deepseek")
    return out
