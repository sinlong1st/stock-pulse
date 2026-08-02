"""Validated shape of the AI's part of a prediction.

The AI only writes the *narrative* — a per-horizon lean + rationale, and the
drivers. The real numbers (price, discount, trend) are added by the assembler,
not the model. Raw output is never trusted: it must parse into these models,
exactly like `ClassificationResult` / `BriefingResult`.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Lean = Literal["bounce", "dip", "hold"]
Confidence = Literal["low", "medium", "high"]
EntryAssessment = Literal["good", "fair", "wait"]

_ENTRY_SYNONYMS = {
    "buy": "good", "attractive": "good", "cheap": "good", "strong": "good", "yes": "good",
    "ok": "fair", "neutral": "fair", "reasonable": "fair", "hold": "fair",
    "avoid": "wait", "overpriced": "wait", "expensive": "wait", "patience": "wait", "no": "wait",
}

_LEAN_SYNONYMS = {
    "up": "bounce", "bullish": "bounce", "rise": "bounce", "rebound": "bounce", "bull": "bounce",
    "down": "dip", "bearish": "dip", "fall": "dip", "drop": "dip", "bear": "dip",
    "flat": "hold", "neutral": "hold", "sideways": "hold", "stay": "hold", "hold": "hold",
}
_CONF_SYNONYMS = {"med": "medium", "moderate": "medium", "mid": "medium", "hi": "high", "lo": "low"}


class HorizonRead(BaseModel):
    model_config = ConfigDict(extra="ignore")

    horizon: str
    lean: Lean = "hold"
    confidence: Confidence = "low"
    rationale: str = ""

    @field_validator("lean", mode="before")
    @classmethod
    def _norm_lean(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip().lower()
            return _LEAN_SYNONYMS.get(s, s)
        return v

    @field_validator("confidence", mode="before")
    @classmethod
    def _norm_conf(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip().lower()
            return _CONF_SYNONYMS.get(s, s)
        return v


class EntryRead(BaseModel):
    """The AI's read on whether the *current* price is a good entry."""

    model_config = ConfigDict(extra="ignore")

    assessment: EntryAssessment = "fair"
    note: str = ""  # e.g. "Fair here; a better entry sits near the $58 support."

    @field_validator("assessment", mode="before")
    @classmethod
    def _norm(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip().lower()
            return _ENTRY_SYNONYMS.get(s, s)
        return v


class PredictionRead(BaseModel):
    """The AI narrative layer (validated). Numbers come from signals separately."""

    model_config = ConfigDict(extra="ignore")

    horizons: list[HorizonRead] = []
    drivers: list[str] = []
    entry: EntryRead = Field(default_factory=EntryRead)

    @field_validator("drivers", mode="before")
    @classmethod
    def _clean_drivers(cls, v: object) -> object:
        if isinstance(v, list):
            return [str(d).strip() for d in v if str(d).strip()]
        return v or []
