"""Deterministic risk rules that can override the AI's entry advice.

Committee plan Phase 1, implementing the vetoes from §15 of the committee spec
against the evidence Predict already produces.

The principle: **a language model must not have sole authority over a risk
decision.** The AI writes the reasoning; this decides whether the setup clears
basic discipline. Everything here is arithmetic over real numbers, so a veto is
explainable and testable — and it costs nothing per prediction.

Rules only ever make the advice *more* cautious. `wait` never becomes `good`.
That asymmetry is deliberate: the downside of a missed entry is an opportunity;
the downside of a bad entry is money.

Each rule returns a structured verdict rather than English, so the app can phrase
it in the user's language — the same rule the rest of this project follows.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Entry assessments, weakest-to-strongest, so a downgrade is a max() on the index.
_CAUTION_ORDER = ("good", "fair", "wait")


@dataclass(frozen=True)
class RuleFinding:
    """One rule's verdict. `code` is stable; the app maps it to localized text."""

    code: str
    # Facts the message needs, e.g. {"days": 3}. Never pre-formatted prose.
    params: dict = field(default_factory=dict)
    # The weakest assessment this rule will allow through.
    caps_at: str = "wait"


@dataclass
class RuleResult:
    original: str  # what the AI said
    final: str  # what we show after vetoes
    findings: list[RuleFinding]

    @property
    def overridden(self) -> bool:
        return self.final != self.original

    def as_dict(self) -> dict:
        return {
            "original": self.original,
            "final": self.final,
            "overridden": self.overridden,
            "findings": [{"code": f.code, "params": f.params} for f in self.findings],
        }


def _cap(current: str, limit: str) -> str:
    """Return whichever of the two is more cautious."""
    try:
        return _CAUTION_ORDER[
            max(_CAUTION_ORDER.index(current), _CAUTION_ORDER.index(limit))
        ]
    except ValueError:
        return limit


def evaluate(
    assessment: str,
    evidence: dict,
    *,
    min_reward_risk: float = 1.5,
    avoid_earnings_within_days: int = 2,
) -> RuleResult:
    """Apply the risk rules to an AI entry assessment.

    `evidence` is the block `service._evidence` builds. Missing values are
    treated as unknown — a rule that can't be evaluated stays silent rather than
    guessing, except RULE-DATA-001 which exists to catch exactly that.
    """
    assessment = assessment if assessment in _CAUTION_ORDER else "fair"
    findings: list[RuleFinding] = []
    final = assessment

    indicators = evidence.get("indicators") or {}
    atr = indicators.get("atr14")
    price = evidence.get("price")
    support_pct = evidence.get("supportPct")
    reward_risk = evidence.get("rewardRisk")
    invalidation = evidence.get("invalidation")
    earnings_in = evidence.get("earningsInDays")
    regime = indicators.get("volatilityRegime")

    def add(code: str, caps_at: str, **params) -> None:
        nonlocal final
        findings.append(RuleFinding(code=code, params=params, caps_at=caps_at))
        final = _cap(final, caps_at)

    # RULE-DATA-001 — can't judge a setup without its floor or its typical range.
    if not evidence.get("enoughHistory") or evidence.get("nearestSupport") is None:
        add("missing-data", "wait")

    # RULE-EARN-001 — a report inside the horizon dominates any technical read.
    if (
        earnings_in is not None
        and 0 <= earnings_in <= avoid_earnings_within_days
    ):
        add("earnings-imminent", "wait", days=earnings_in)

    # RULE-RR-001 — not enough upside to justify the downside.
    if reward_risk is not None and reward_risk < min_reward_risk:
        add(
            "weak-reward-risk",
            "wait",
            ratio=round(reward_risk, 2),
            minimum=min_reward_risk,
        )

    # RULE-VOL-001 — extreme volatility makes every level unreliable.
    if regime == "extreme":
        add("extreme-volatility", "wait")
    elif regime == "high" and assessment == "good":
        # Not a veto, but "good" overstates it when the range is this wide.
        # Guarded on the ORIGINAL assessment, not the running one — otherwise
        # whether this fires would depend on which rules ran before it.
        add("high-volatility", "fair")

    # RULE-CHASE-001 — more than 1 ATR above the nearest support is a chase:
    # the entry the advice is built on has already gone.
    if atr and price and support_pct is not None and atr > 0:
        distance = abs(support_pct) / 100 * price
        if distance > atr:
            add("chasing", "fair", atrs=round(distance / atr, 1))

    # RULE-STOP-001 — an invalidation closer than half an ATR is inside the noise
    # and will be hit by an ordinary day's movement.
    if atr and price and invalidation and atr > 0:
        stop_distance = price - invalidation
        if stop_distance <= 0:
            add("invalid-stop", "wait")
        elif stop_distance < atr * 0.5:
            add("stop-too-tight", "wait", atrs=round(stop_distance / atr, 2))

    return RuleResult(original=assessment, final=final, findings=findings)
