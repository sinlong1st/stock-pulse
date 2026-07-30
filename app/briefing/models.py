"""Validated shape of a market briefing.

Raw model output is never trusted directly — it must parse and validate into
these models first, exactly like `ClassificationResult` for the alert flow.
Validators are lenient (normalize case, map synonyms, default missing fields)
because the model's JSON is only mostly well-behaved.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

Urgency = Literal["routine", "notable", "urgent"]
Direction = Literal["bullish", "bearish", "mixed"]
Trend = Literal["new", "strengthening", "fading", "reversing"]
Freshness = Literal["new", "background"]

_DIRECTION_SYNONYMS = {
    "positive": "bullish",
    "good": "bullish",
    "up": "bullish",
    "bull": "bullish",
    "negative": "bearish",
    "bad": "bearish",
    "down": "bearish",
    "bear": "bearish",
    "neutral": "mixed",
    "uncertain": "mixed",
}

_URGENCY_SYNONYMS = {
    "low": "routine",
    "normal": "routine",
    "medium": "notable",
    "moderate": "notable",
    "high": "urgent",
    "critical": "urgent",
}


class BriefingTheme(BaseModel):
    """One storyline in the briefing (e.g. "AI & semiconductors")."""

    model_config = ConfigDict(extra="ignore")

    theme: str
    direction: Direction = "mixed"
    tickers: list[str] = []
    insight: str
    trend: Trend = "new"
    freshness: Freshness = "new"
    event_time: str | None = None
    sources: list[str] = []

    @field_validator("direction", mode="before")
    @classmethod
    def _norm_direction(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip().lower()
            return _DIRECTION_SYNONYMS.get(s, s)
        return v

    @field_validator("trend", "freshness", mode="before")
    @classmethod
    def _lower(cls, v: object) -> object:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("tickers", mode="before")
    @classmethod
    def _norm_tickers(cls, v: object) -> object:
        if isinstance(v, list):
            return [str(t).strip().upper() for t in v if str(t).strip()]
        return v or []


class WatchlistNote(BaseModel):
    """A short note tied to a specific watchlist ticker."""

    model_config = ConfigDict(extra="ignore")

    ticker: str
    note: str
    direction: Direction = "mixed"

    @field_validator("ticker", mode="before")
    @classmethod
    def _upper(cls, v: object) -> object:
        return str(v).strip().upper() if v is not None else v

    @field_validator("direction", mode="before")
    @classmethod
    def _norm_direction(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip().lower()
            return _DIRECTION_SYNONYMS.get(s, s)
        return v


class BriefingResult(BaseModel):
    """Validated analyst read for one briefing run."""

    model_config = ConfigDict(extra="ignore")

    has_material_update: bool
    urgency: Urgency = "routine"
    headline: str = ""
    themes: list[BriefingTheme] = []
    watchlist_notes: list[WatchlistNote] = []
    risk_flags: list[str] = []

    @field_validator("urgency", mode="before")
    @classmethod
    def _norm_urgency(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip().lower()
            return _URGENCY_SYNONYMS.get(s, s)
        return v

    @field_validator("risk_flags", mode="before")
    @classmethod
    def _clean_flags(cls, v: object) -> object:
        if isinstance(v, list):
            out = []
            for f in v:
                s = str(f).strip()
                # Drop empties and any echo of the schema's placeholder text.
                if s and "worth watching, if any" not in s.lower():
                    out.append(s)
            return out
        return v or []
