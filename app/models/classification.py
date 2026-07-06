"""The AI classification result model.

This is the strict, validated shape the application uses. Raw AI output is
never trusted directly — it must parse and validate into this model first.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

Importance = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
Category = Literal["MACRO", "TICKER", "SECTOR", "OTHER"]


class ClassificationResult(BaseModel):
    """Validated AI analysis of a single article."""

    model_config = ConfigDict(extra="ignore")

    is_market_relevant: bool
    importance: Importance
    category: Category
    related_tickers: list[str] = []
    summary: str
    why_it_matters: str
    should_alert: bool
    confidence: float | None = None

    @field_validator("importance", "category", mode="before")
    @classmethod
    def _upper(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

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
