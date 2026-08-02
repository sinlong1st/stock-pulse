"""Prediction strategies — the natural-language framework the AI reasons with.

A strategy shapes *how* the AI weighs the (real) signals + news into a lean — it
never changes the numbers, the output format, or the disclaimers (those are fixed
guardrails in the analyst). The built-in default is visible to users for
transparency; custom per-user strategies come in the Pro/multi-user era.
See specs/STOCKPULSE_AI_PREDICTION_PLAN.md §5.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Strategy:
    id: str
    name: str
    body: str  # the natural-language framework
    builtin: bool = True


DEFAULT_STRATEGY = Strategy(
    id="default",
    name="StockPulse Balanced",
    body=(
        "Weigh three things for each horizon: (1) the materiality and direction of "
        "recent news, (2) the price trend, and (3) where the price sits in its range. "
        "A large discount can set up a bounce, but a falling trend can keep falling — "
        "don't call a bottom on cheapness alone. Short horizons (about a week) are "
        "driven mostly by fresh news and momentum; longer horizons (a month, three "
        "months) lean more on the trend and where value sits. When the signals "
        "conflict or the news is thin, prefer 'hold' with low confidence. Be honest "
        "and never imply certainty."
    ),
    builtin=True,
)
