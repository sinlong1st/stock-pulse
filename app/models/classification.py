"""The AI classification result model.

This is the strict, validated shape the application uses. Raw AI output is
never trusted directly — it must parse and validate into this model first.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

Importance = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
Category = Literal["MACRO", "TICKER", "SECTOR", "OTHER"]
Sentiment = Literal["BULLISH", "BEARISH", "NEUTRAL"]

# Synonyms the AI might return, mapped to our canonical sentiment values.
_SENTIMENT_SYNONYMS = {
    "POSITIVE": "BULLISH",
    "GOOD": "BULLISH",
    "UP": "BULLISH",
    "BULL": "BULLISH",
    "NEGATIVE": "BEARISH",
    "BAD": "BEARISH",
    "DOWN": "BEARISH",
    "BEAR": "BEARISH",
    "MIXED": "NEUTRAL",
    "UNCERTAIN": "NEUTRAL",
    "NONE": "NEUTRAL",
}


class ClassificationResult(BaseModel):
    """Validated AI analysis of a single article."""

    model_config = ConfigDict(extra="ignore")

    is_market_relevant: bool
    importance: Importance
    category: Category
    # Directional read of the news for the related stock(s): the AI's opinion
    # on the news, not a price prediction.
    sentiment: Sentiment = "NEUTRAL"
    related_tickers: list[str] = []
    summary: str
    why_it_matters: str
    should_alert: bool
    confidence: float | None = None

    @field_validator("importance", "category", mode="before")
    @classmethod
    def _upper(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("sentiment", mode="before")
    @classmethod
    def _normalize_sentiment(cls, value: object) -> object:
        if value is None:
            return "NEUTRAL"
        if isinstance(value, str):
            v = value.strip().upper()
            return _SENTIMENT_SYNONYMS.get(v, v)
        return value

    @field_validator("related_tickers", mode="before")
    @classmethod
    def _normalize_tickers(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(t).strip().upper() for t in value if str(t).strip()]
        return value

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return max(0.0, min(1.0, value))
