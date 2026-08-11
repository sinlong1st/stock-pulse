"""Deterministic exit rules over the position analysis (spec §28).

Exit-advisor plan Phase 6. The mechanism is lifted from
`app/prediction/rules.py`, which already proved it: arithmetic over real numbers,
structured findings rather than English, and a language model never holding sole
authority over a risk decision.

**The ladder runs the other way here.** Predict's rules only ever move advice
toward *not buying*. These only ever move it toward *lower exposure*:

    hold → hold-with-stop → partial-sell → reduce → exit

A rule may never talk you into holding more. That asymmetry is the whole point:
these fire when something in the evidence says the position is riskier than the
headline reads, and "riskier than it looks" is never an argument for size.

Two consequences worth stating, because they look like omissions:

- **RULE-EXIT-010 is a suppressor, not an upgrade.** "Don't sell just because RSI
  is high, if this is a real breakout" cancels the extension rule; it cannot
  promote anything. Implemented as a veto over RULE-EXIT-009 so the ladder stays
  one-directional.
- **Every rule reads the ORIGINAL evidence**, never the running verdict, so the
  findings do not depend on the order the rules run in. Predict had that exact
  bug once and it was invisible until a test went looking for it.

RULE-EXIT-002, -003 and -012 (shares > 0, average cost > 0, sane sell
percentages) are absent on purpose: `app/position/math.py` enforces them at
parse time, so an analysis that reaches this engine has already satisfied them.
Re-checking here would be a second definition of valid, which is how two
definitions start to disagree.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The exposure ladder, most exposed first. A rule names the least reduction it
# will accept; the result is whichever demand is strongest.
EXPOSURE_LADDER = ("hold", "hold-with-stop", "partial-sell", "reduce", "exit")

# §3.3 allows nine actions; they collapse onto five rungs. Actions that express
# a *stance* rather than a size ("no clear edge") sit at full exposure, because
# that is what they leave you holding.
_LADDER_POSITION = {
    "hold": 0,
    "wait-for-confirmation": 0,
    "no-clear-edge": 0,
    "hold-with-stop": 1,
    "hold-only-above-support": 1,
    "partial-sell": 2,
    "take-profit": 2,
    "sell-into-strength": 2,
    "reduce": 3,
    "exit": 4,
}

# How many deterioration signals must agree before trend damage is called.
# Three, because any one of them fires constantly in an ordinary pullback.
_DETERIORATION_THRESHOLD = 3

# Extension thresholds (RULE-EXIT-009), in the stock's own units.
_EXTENDED_ATRS = 2.0
_OVERBOUGHT_RSI = 70.0
_NEAR_RESISTANCE_ATRS = 0.5

# A floor this close is inside one ordinary day's movement, so any reward/risk
# built on it is arithmetic rather than a plan. Mirrors RULE-STOP-001.
_NOISE_ATRS = 0.5

# Relative volume that confirms a breakout is real participation, not drift.
_BREAKOUT_VOLUME = 1.3


@dataclass(frozen=True)
class ExitFinding:
    """One rule's verdict. `code` is stable; the app maps it to localized text."""

    code: str
    # Facts the message needs, e.g. {"days": 3}. Never pre-formatted prose.
    params: dict = field(default_factory=dict)
    # The least exposure reduction this rule will accept, or None when the
    # finding is informational (it changes what the app may *say*, not what the
    # user should hold).
    at_least: str | None = None


@dataclass
class ExitRuleResult:
    original: str | None  # what the AI said, or None before Phase 5 exists
    final: str | None  # what we show after the rules have had their say
    findings: list[ExitFinding]
    # §28 RULE-EXIT-001: no sell/hold conclusion may be drawn from a stale quote.
    refresh_required: bool = False

    @property
    def overridden(self) -> bool:
        return self.original is not None and self.final != self.original

    def as_dict(self) -> dict:
        return {
            "original": self.original,
            "final": self.final,
            "overridden": self.overridden,
            "refreshRequired": self.refresh_required,
            "findings": [
                {"code": f.code, "params": f.params, "atLeast": f.at_least}
                for f in self.findings
            ],
        }


def _rung(action: str | None) -> int:
    return _LADDER_POSITION.get(action or "", 0)


def _at_least(current: str | None, demand: str) -> str:
    """Whichever of the two leaves less exposure."""
    if current is None:
        return demand
    return current if _rung(current) >= _rung(demand) else demand


def _deterioration_signals(evidence: dict) -> list[str]:
    """Which of §28's trend-damage signals are actually present.

    Returned as a list rather than a count so the app can show *which* ones —
    "below its 20-day average and MACD rolling over" is a reason; "3 signals"
    is a number.
    """
    indicators = evidence.get("indicators") or {}
    price = evidence.get("price")
    macd = indicators.get("macd") or {}
    market = evidence.get("market") or {}

    signals: list[str] = []
    if evidence.get("trend") == "down":
        signals.append("trend-down")
    if price and indicators.get("sma20") and price < indicators["sma20"]:
        signals.append("below-sma20")
    if price and indicators.get("ema21") and price < indicators["ema21"]:
        signals.append("below-ema21")
    if macd.get("histogram") is not None and macd["histogram"] < 0:
        signals.append("macd-negative")
    relative = market.get("relative20d")
    if relative is not None and relative < 0:
        signals.append("lagging-market")
    return signals


def _is_valid_breakout(evidence: dict) -> bool:
    """RULE-EXIT-010 — a real breakout, which must not be sold merely for being
    extended.

    All four have to hold: price above the last ceiling, participation confirming
    it, the market not actively hostile, and no event inside the window. Any
    weaker test would cancel the extension rule on ordinary strength, which is
    exactly when the extension rule is worth having.
    """
    resistance = evidence.get("resistance")
    price = evidence.get("price")
    relative_volume = evidence.get("relativeVolume")
    risk_appetite = (evidence.get("market") or {}).get("riskAppetite")
    earnings_in = evidence.get("earningsInDays")

    broke_out = bool(price and resistance and price > resistance)
    confirmed = relative_volume is not None and relative_volume >= _BREAKOUT_VOLUME
    market_ok = risk_appetite != "risk-off"
    no_event = earnings_in is None or earnings_in > 5
    return broke_out and confirmed and market_ok and no_event


def evaluate(
    action: str | None,
    evidence: dict,
    *,
    min_hold_reward_risk: float = 1.0,
    earnings_within_days: int = 3,
    stale_quote_minutes: float = 20.0,
) -> ExitRuleResult:
    """Apply the exit rules to a position analysis.

    `action` is the AI's recommendation once Phase 5 exists. Passing ``None``
    (the numbers-only path) still evaluates every rule and reports the least
    exposure the evidence justifies — which is what makes this engine useful
    before any model is wired in.

    `evidence` is the flat dict `service._rule_evidence` builds. A value that
    is missing is *unknown*, and a rule that cannot be evaluated stays silent
    rather than guessing.
    """
    findings: list[ExitFinding] = []
    final = action
    refresh_required = False

    def add(code: str, at_least: str | None = None, **params) -> None:
        nonlocal final
        findings.append(ExitFinding(code=code, params=params, at_least=at_least))
        if at_least:
            final = _at_least(final, at_least)

    # RULE-EXIT-001 — a stale quote during a live session. No conclusion may
    # rest on it, so this blocks rather than moving the ladder.
    age = evidence.get("quoteAgeMinutes")
    if evidence.get("sessionToday") and age is not None and age > stale_quote_minutes:
        refresh_required = True
        add("stale-quote", None, minutes=round(age))

    # RULE-EXIT-004 — a stop at or above the current price isn't a stop.
    stop, price = evidence.get("stop"), evidence.get("price")
    if stop is not None and price is not None and stop >= price:
        add("invalid-stop", None, stop=stop, price=price)

    # RULE-EXIT-005 — a report inside the window dominates any technical read.
    # Not a sell signal: it means a plain HOLD is an active choice to take event
    # risk, so the position needs a defined stop at minimum.
    earnings_in = evidence.get("earningsInDays")
    if earnings_in is not None and 0 <= earnings_in <= earnings_within_days:
        add("earnings-imminent", "hold-with-stop", days=earnings_in)

    # RULE-EXIT-006 — the incremental trade no longer pays. §28 is explicit that
    # this biases toward trimming and must NOT force a full exit: a poor ratio
    # from here is a reason to take some off, not to abandon the position.
    reward_risk = evidence.get("holdRewardRisk")
    if reward_risk is not None and reward_risk < min_hold_reward_risk:
        add(
            "weak-hold-reward-risk",
            "partial-sell",
            ratio=round(reward_risk, 2),
            minimum=min_hold_reward_risk,
        )

    # RULE-EXIT-007 — price has fallen through the near-term floor structure;
    # there is nothing recent left underneath it.
    if evidence.get("enoughHistory") and not evidence.get("hasNearSupport"):
        add("support-broken", "reduce")

    # RULE-EXIT-008 — the trend that justified holding is coming apart.
    deterioration = _deterioration_signals(evidence)
    if len(deterioration) >= _DETERIORATION_THRESHOLD:
        add("trend-deterioration", "partial-sell", signals=deterioration)

    # RULE-EXIT-009 / -010 — extended enough that some profit-taking is the
    # percentage play, unless this is a genuine breakout (§28 is emphatic: do
    # not sell merely because RSI is high).
    indicators = evidence.get("indicators") or {}
    above_atrs = evidence.get("aboveSma20Atrs")
    rsi = indicators.get("rsi14")
    resistance_atrs = evidence.get("resistanceAtrs")
    stretched = above_atrs is not None and above_atrs >= _EXTENDED_ATRS
    overbought_at_ceiling = (
        rsi is not None
        and rsi >= _OVERBOUGHT_RSI
        and resistance_atrs is not None
        and resistance_atrs <= _NEAR_RESISTANCE_ATRS
    )
    if stretched or overbought_at_ceiling:
        if _is_valid_breakout(evidence):
            add("valid-breakout", None)  # informational: says why we did nothing
        else:
            add("extended", "partial-sell", atrs=above_atrs, rsi=rsi)

    # RULE-EXIT-011 — below cost. Nothing here may be phrased as profit-taking,
    # and the app needs telling because the dollar figures alone don't say so.
    if evidence.get("inProfit") is False:
        add("below-cost", None)

    # The exit mirror of RULE-STOP-001, added after a live WDC run returned a
    # 6.62:1 "strong" hold reward/risk measured against a floor 0.13 ATR away —
    # real arithmetic resting on a level an ordinary day takes out. The ratio is
    # not wrong, so this doesn't move the ladder; it says how far to trust it.
    support_atrs = evidence.get("supportAtrs")
    if support_atrs is not None and 0 < support_atrs < _NOISE_ATRS:
        add("support-inside-noise", None, atrs=support_atrs)

    return ExitRuleResult(
        original=action,
        final=final,
        findings=findings,
        refresh_required=refresh_required,
    )
