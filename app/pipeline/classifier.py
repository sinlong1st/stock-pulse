"""AI classification stage (pipeline Step 5).

The classifier is isolated behind an interface so the provider can be
swapped later. The OpenAI implementation calls the chat completions API in
JSON mode and validates the result into a strict `ClassificationResult`.
Raw model output is never trusted directly.
"""

import json
import logging
from abc import ABC, abstractmethod

import httpx
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.models.article import NewsArticle
from app.models.classification import ClassificationResult
from app.watchlist import get_watchlist_config

logger = logging.getLogger("stockpulse.classifier")


class ClassificationError(Exception):
    """Raised when classification fails (API error or invalid output)."""


class Classifier(ABC):
    """Analyzes an article and returns a validated classification."""

    @abstractmethod
    async def classify(self, article: NewsArticle) -> ClassificationResult:
        raise NotImplementedError


_SYSTEM_PROMPT = (
    "You are a financial news classifier for a market-alert service. "
    "Given a news article, decide whether it is market-relevant and how "
    "important it is. Respond ONLY with a JSON object using exactly these keys:\n"
    '  "is_market_relevant" (boolean),\n'
    '  "importance" (one of "LOW", "MEDIUM", "HIGH", "CRITICAL"),\n'
    '  "category" (one of "MACRO", "TICKER", "SECTOR", "OTHER"),\n'
    '  "related_tickers" (array of uppercase ticker symbols, possibly empty),\n'
    '  "summary" (one concise sentence),\n'
    '  "why_it_matters" (one concise sentence),\n'
    '  "should_alert" (boolean),\n'
    '  "confidence" (number between 0 and 1).\n'
    "Be conservative: only mark HIGH/CRITICAL for genuinely market-moving news. "
    "Prefer tickers from the user's watchlist when relevant."
)


def _build_user_prompt(article: NewsArticle, watchlist: list[str]) -> str:
    return (
        f"Watchlist: {', '.join(watchlist)}\n\n"
        f"Title: {article.title}\n"
        f"Summary: {article.summary or '(none)'}\n"
        f"Source: {article.source}"
    )


class OpenAIClassifier(Classifier):
    """Classifier backed by the OpenAI chat completions API."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        watchlist: list[str] | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ClassificationError("OPENAI_API_KEY is not set.")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.watchlist = watchlist if watchlist is not None else list(get_watchlist_config().tickers)
        self.timeout = timeout
        self._transport = transport

    async def classify(self, article: NewsArticle) -> ClassificationResult:
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(article, self.watchlist)},
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
            raise ClassificationError(f"OpenAI request failed: {exc}") from exc

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ClassificationError(f"Unexpected OpenAI response shape: {exc}") from exc

    @staticmethod
    def _parse(content: str) -> ClassificationResult:
        try:
            raw = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ClassificationError(f"AI did not return valid JSON: {exc}") from exc
        try:
            return ClassificationResult.model_validate(raw)
        except ValidationError as exc:
            raise ClassificationError(f"AI output failed validation: {exc}") from exc


def build_classifier(settings: Settings | None = None) -> Classifier:
    """Construct the configured classifier. Raises if no API key is set."""
    settings = settings or get_settings()
    return OpenAIClassifier(
        settings.openai_api_key,
        model=settings.openai_model,
        base_url=settings.openai_base_url,
    )
