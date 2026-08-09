"""How much the two analysts actually agree.

Committee plan Phase 4, implementing §11 of the committee spec against the two
reads Predict already produces. Like the rule engine, this is pure arithmetic —
no LLM call, no cost, fully testable.

Until now "do they agree?" was one boolean on the entry assessment. That misses
the two disagreements that matter most: the models can pick the same entry
grade while leaning in *opposite directions* on the horizons, or agree on
everything while being miles apart on how sure they are.

The output is also the early-stop gate for Phase 5. A debate round costs real
money, so it should only run when the reads genuinely conflict — `requires_debate`
is what decides that. Nothing consumes it yet.

**Agreement is not evidence of correctness.** Two models trained on overlapping
data produce correlated errors; they can agree confidently and both be wrong.
This measures consistency, not truth, and the app must not present it as a
second vote of confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Entry grades mapped to the spec's coarser action categories (§11.1). Our
# vocabulary is smaller than the spec's nine actions, so the mapping collapses
# rather than invents: `fair` is conditional — a yes with a caveat.
_ACTION_CATEGORY = {
    "good": "enter",
    "fair": "conditional-enter",
    "wait": "wait",
}

# Ordered weakest-to-strongest so distance between two grades is an index gap.
_ENTRY_ORDER = ("good", "fair", "wait")

# Ordinal, deliberately not 0-1 floats. The spec assumes a continuous 0-1
# confidence and thresholds the gap at 0.25; our analysts emit three levels.
# Inventing decimals to fit the spec's threshold would be exactly the false
# precision §3.5 warns against, so the gap here is counted in *steps*.
_CONFIDENCE_ORDER = ("low", "medium", "high")

# Two steps (low vs high) is a material gap. One step is normal analyst spread.
_MATERIAL_CONFIDENCE_STEPS = 2

_OPPOSED = frozenset({frozenset({"bounce", "dip"})})


@dataclass(frozen=True)
class Difference:
    """One concrete disagreement. `code` is stable; the app localizes it."""

    code: str
    params: dict = field(default_factory=dict)


@dataclass
class AgreementResult:
    action_agreement: str  # "strong" | "partial" | "conflict"
    direction_agreement: bool
    confidence_steps: int  # 0, 1 or 2 — see _CONFIDENCE_ORDER
    differences: list[Difference]

    @property
    def requires_debate(self) -> bool:
        """Whether a Phase 5 debate round would be worth paying for.

        Deliberately conservative: a debate is only justified when the reads
        actually pull apart, not merely when they differ in emphasis.
        """
        return (
            self.action_agreement == "conflict"
            or not self.direction_agreement
            or self.confidence_steps >= _MATERIAL_CONFIDENCE_STEPS
        )

    def as_dict(self) -> dict:
        return {
            "actionAgreement": self.action_agreement,
            "directionAgreement": self.direction_agreement,
            "confidenceSteps": self.confidence_steps,
            "requiresDebate": self.requires_debate,
            "differences": [{"code": d.code, "params": d.params} for d in self.differences],
        }


def _index(order: tuple[str, ...], value: str) -> int | None:
    try:
        return order.index(value)
    except ValueError:
        return None


def _action_agreement(primary: str, second: str) -> str:
    """`strong` when the grades match, `conflict` at the extremes, else `partial`."""
    if primary == second:
        return "strong"
    if _ACTION_CATEGORY.get(primary) == _ACTION_CATEGORY.get(second):
        return "strong"
    a, b = _index(_ENTRY_ORDER, primary), _index(_ENTRY_ORDER, second)
    if a is None or b is None:
        # An unrecognised grade is not evidence of agreement. Say so rather than
        # defaulting to "strong" and quietly suppressing a real conflict.
        return "conflict"
    # good vs wait — one says buy, the other says stay out. That is the §11.2
    # "one says enter and the other says avoid" case.
    return "conflict" if abs(a - b) >= 2 else "partial"


def _confidence_steps(primary_reads, second_reads) -> int:
    """Largest per-horizon confidence gap, in ordinal steps.

    Max rather than mean: one horizon where the models are far apart is the
    interesting signal, and averaging would dilute it away.
    """
    by_horizon = {h.horizon: h for h in second_reads}
    widest = 0
    for read in primary_reads:
        other = by_horizon.get(read.horizon)
        if other is None:
            continue
        a = _index(_CONFIDENCE_ORDER, read.confidence)
        b = _index(_CONFIDENCE_ORDER, other.confidence)
        if a is None or b is None:
            continue
        widest = max(widest, abs(a - b))
    return widest


def evaluate(primary, second) -> AgreementResult:
    """Compare two `PredictionRead`s. Order matters only for reporting.

    Both arguments are full reads, not the trimmed second-opinion payload — the
    comparison needs the horizon leans, which that payload flattens.
    """
    differences: list[Difference] = []

    action = _action_agreement(primary.entry.assessment, second.entry.assessment)
    if action != "strong":
        differences.append(
            Difference(
                "entry-differs",
                {"primary": primary.entry.assessment, "second": second.entry.assessment},
            )
        )

    # Direction: only bounce-vs-dip counts as opposed. A `hold` against either is
    # weaker conviction, not a contradiction — treating it as one would send us
    # into a paid debate over a shrug.
    by_horizon = {h.horizon: h for h in second.horizons}
    direction_agreement = True
    for read in primary.horizons:
        other = by_horizon.get(read.horizon)
        if other is None:
            continue
        if frozenset({read.lean, other.lean}) in _OPPOSED:
            direction_agreement = False
            differences.append(
                Difference(
                    "direction-opposed",
                    {"horizon": read.horizon, "primary": read.lean, "second": other.lean},
                )
            )

    steps = _confidence_steps(primary.horizons, second.horizons)
    if steps >= _MATERIAL_CONFIDENCE_STEPS:
        differences.append(Difference("confidence-gap", {"steps": steps}))

    return AgreementResult(
        action_agreement=action,
        direction_agreement=direction_agreement,
        confidence_steps=steps,
        differences=differences,
    )
