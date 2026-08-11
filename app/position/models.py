"""Validated shape of the AI's part of an exit analysis (spec §22).

The model writes the *judgement and the words*. It never writes a number: every
dollar figure, every ratio and every scenario range is computed by
`app/position/math.py` from levels that came out of real price action.

That is enforced structurally rather than by asking nicely. Scenarios and plans
reference levels by **index into a menu the code built** — `lowLevel: 3` — so a
model that hallucinates $500 has no way to express it. The worst it can do is
pick the wrong real level, which is a judgement we can show and argue with.

Mirrors `app/prediction/models.py`: `extra="ignore"`, defaults everywhere, and
synonym normalization, because a model told to answer "partial-sell" will
sometimes answer "Partial Sell" or "trim".
"""

from typing import Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# §3.3's valid recommendations. Deliberately not a binary.
ExitAction = Literal[
    "hold",
    "hold-with-stop",
    "partial-sell",
    "take-profit",
    "reduce",
    "exit",
    "sell-into-strength",
    "wait-for-confirmation",
    "no-clear-edge",
]
Confidence = Literal["low", "medium", "high"]
PlanName = Literal["conservative", "balanced", "aggressive"]
PlanAction = Literal["hold", "partial-sell", "sell-all"]

_ACTION_SYNONYMS = {
    "sell": "exit", "sell all": "exit", "sell-all": "exit", "close": "exit", "liquidate": "exit",
    "trim": "partial-sell", "partial": "partial-sell", "partial sell": "partial-sell",
    "scale out": "partial-sell", "sell some": "partial-sell",
    "take profit": "take-profit", "profit-taking": "take-profit", "take profits": "take-profit",
    "sell into strength": "sell-into-strength",
    "hold with stop": "hold-with-stop", "hold-only-above-support": "hold-with-stop",
    "hold only above support": "hold-with-stop", "stop": "hold-with-stop",
    "keep": "hold", "stay": "hold", "do nothing": "hold",
    "wait": "wait-for-confirmation", "wait for confirmation": "wait-for-confirmation",
    "no edge": "no-clear-edge", "unclear": "no-clear-edge", "neutral": "no-clear-edge",
}
_CONF_SYNONYMS = {"med": "medium", "moderate": "medium", "mid": "medium",
                  "hi": "high", "lo": "low"}


def _norm(value: object, table: dict[str, str]) -> object:
    if isinstance(value, str):
        key = value.strip().lower().replace("_", "-")
        return table.get(key, table.get(key.replace("-", " "), key))
    return value


class ScenarioRead(BaseModel):
    """One of bull / base / bear, bounded by two levels from the offered menu.

    `low_level` / `high_level` hold whatever the model used to point at a menu
    entry — the level's price, or its position in the list. The service resolves
    either against the actual menu and **drops anything that doesn't match**,
    which is what keeps an invented price out (§3.5).

    Live models overwhelmingly answer with the price, so that is what the prompt
    now asks for. Price-matching is also the stronger check: a hallucinated $500
    simply fails to resolve, whereas a hallucinated *index* would quietly land on
    some real level and look like a decision.

    Probabilities are whole percents, renormalized in code to sum to 100 — §20's
    "approximately" isn't good enough when the three sit side by side.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: Literal["bull", "base", "bear"]
    probability: int = 0
    low_level: float | None = Field(
        default=None, validation_alias=AliasChoices("lowLevel", "low_level", "low", "lowPrice")
    )
    high_level: float | None = Field(
        default=None,
        validation_alias=AliasChoices("highLevel", "high_level", "high", "highPrice"),
    )
    trigger: str = ""


class PlanRead(BaseModel):
    """One of the three §24 alternatives.

    Stop and target are level indices for the same reason scenarios are: a plan
    whose stop the model invented is a plan resting on a price that never traded.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: PlanName
    action: PlanAction = "hold"
    sell_pct_now: int | None = Field(
        default=None, validation_alias=AliasChoices("sellPctNow", "sell_pct_now", "sellPct")
    )
    stop_level: float | None = Field(
        default=None, validation_alias=AliasChoices("stopLevel", "stop_level", "stop")
    )
    first_target_level: float | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "firstTargetLevel", "first_target_level", "firstTarget", "target"
        ),
    )
    invalidation_level: float | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "invalidationLevel", "invalidation_level", "invalidation"
        ),
    )
    explanation: str = ""

    @field_validator("action", mode="before")
    @classmethod
    def _norm_action(cls, v: object) -> object:
        got = _norm(v, {"sell": "sell-all", "exit": "sell-all", "trim": "partial-sell"})
        return got

    @field_validator("sell_pct_now", mode="before")
    @classmethod
    def _clamp_pct(cls, v: object) -> object:
        """RULE-EXIT-012's bounds, applied before the number reaches the math."""
        if v is None or v == "":
            return None
        try:
            pct = int(round(float(v)))
        except (TypeError, ValueError):
            return None
        return min(100, max(0, pct)) or None


class ExitRead(BaseModel):
    """The AI narrative layer of an exit analysis (validated)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    action: ExitAction = "no-clear-edge"
    confidence: Confidence = "low"
    thesis: str = ""
    reasons_to_hold: list[str] = Field(default_factory=list, alias="reasonsToHold")
    reasons_to_sell: list[str] = Field(default_factory=list, alias="reasonsToSell")
    warnings: list[str] = Field(default_factory=list)
    scenarios: list[ScenarioRead] = Field(default_factory=list)
    plans: list[PlanRead] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _listify(cls, data: object) -> object:
        """Accept `{"conservative": {...}, "balanced": {...}}` for plans/scenarios.

        A live gpt-4o-mini run returned exactly that: the names asked for as
        *keys* rather than as a `name` field. It is a reasonable reading of the
        instruction and the content was fine, so rejecting the whole analysis
        over the container shape would be throwing away a good answer on a
        technicality.
        """
        if not isinstance(data, dict):
            return data
        for key in ("plans", "scenarios"):
            value = data.get(key)
            if isinstance(value, dict):
                data[key] = [
                    {**item, "name": name}
                    for name, item in value.items()
                    if isinstance(item, dict)
                ]
        return data

    @field_validator("action", mode="before")
    @classmethod
    def _norm_action(cls, v: object) -> object:
        return _norm(v, _ACTION_SYNONYMS)

    @field_validator("confidence", mode="before")
    @classmethod
    def _norm_confidence(cls, v: object) -> object:
        return _norm(v, _CONF_SYNONYMS)

    @field_validator("reasons_to_hold", "reasons_to_sell", "warnings", mode="before")
    @classmethod
    def _clean_list(cls, v: object) -> object:
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()][:4]
        return []
