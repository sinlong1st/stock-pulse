"""Position arithmetic for the Exit Advisor (plan Phase 1, spec §5-§8, §20, §31).

Every dollar figure the feature shows is computed here. **No AI touches any of
it** — the same rule the rest of this project follows, and it matters more here
than anywhere else: a model that miscounts a user's profit by $200 is worse than
a model that says nothing.

Three conventions worth knowing:

- **Decimal, not float.** These are user-entered dollar amounts multiplied by
  share counts, and `0.1 + 0.2` problems surface as a P&L a cent off from the
  brokerage's. Inputs arrive as JSON numbers and are converted via `str()`,
  which is what stops the float artifact from being baked in before we start.
  Deliberately confined to this module — `signals.py` and `indicators.py` take
  floats from Yahoo and should stay that way.
- **Missing is a fact, not a zero.** Anything undefined for the inputs given
  (hold reward/risk with no downside leg, a giveback percentage on a losing
  position) returns ``None``. The rule engine and the app both act on that;
  a fabricated 0.0 would read as a real, terrible number.
- **Structured values, never English.** Interpretation comes back as a stable
  code (`strong`, `weak`, ...) which the app localizes, matching how the rule
  engine reports findings.

The framing throughout is §3.2: hold-vs-sell is judged from the **current price
forward**. Average cost sets the emotional context and the tax bill, but the
question "is the remaining upside worth the remaining risk?" does not depend on
what you paid.

Flow: `parse_position` + `parse_price` validate → `summarize` produces the
`PositionSummary` every other function takes. Passing the summary rather than a
position-plus-price pair means a caller cannot accidentally value a position at
a price it wasn't measured against.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation

CENTS = Decimal("0.01")
HUNDRED = Decimal("100")
ZERO = Decimal("0")
ONE = Decimal("1")

# §6's interpretation bands, richest first. The label is a code; the app writes
# the sentence. These describe *incremental* hold value — the reward for staying
# in from here — not the quality of the original purchase.
_REWARD_RISK_BANDS: tuple[tuple[Decimal, str], ...] = (
    (Decimal("2.00"), "strong"),
    (Decimal("1.50"), "attractive"),
    (Decimal("1.00"), "balanced"),
    (Decimal("0.75"), "weak"),
)
_REWARD_RISK_FLOOR = "poor"

# The presets §8 requires. Any other percentage is the spec's "custom".
PARTIAL_SELL_PRESETS: tuple[int, ...] = (25, 33, 50, 75)


class PositionError(ValueError):
    """An input that makes the whole calculation meaningless.

    Raised for the spec's RULE-EXIT-002 and RULE-EXIT-003 (shares and average
    cost must both be positive) and for an unusable price. These are
    request-validation failures, not analysis findings — there is nothing to
    reason about until they are fixed.
    """


def to_decimal(value: object, *, field: str) -> Decimal:
    """Convert a JSON number / string to Decimal without inheriting float error.

    `Decimal(0.1)` is 0.1000000000000000055511151231257827 but `Decimal("0.1")`
    is exactly 0.1, so floats go through `str()` first. That is the entire
    reason this helper exists rather than calling `Decimal()` at each site.
    """
    if isinstance(value, Decimal):
        got = value
    elif isinstance(value, bool):
        # bool is an int subclass, so a True that slipped through as a share
        # count would silently become 1 share.
        raise PositionError(f"{field} must be a number")
    elif isinstance(value, int | float | str):
        try:
            got = Decimal(str(value).strip())
        except (InvalidOperation, ValueError) as exc:
            raise PositionError(f"{field} must be a number") from exc
    else:
        raise PositionError(f"{field} must be a number")

    if not got.is_finite():  # NaN and infinity both arrive as valid Decimals
        raise PositionError(f"{field} must be a finite number")
    return got


def _money(value: Decimal) -> Decimal:
    """Round to cents, half-up — how money is quoted, not banker's rounding."""
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def _pct(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def _whole(value: Decimal) -> Decimal:
    return value.quantize(ZERO, rounding=ROUND_DOWN)


def _f(value: Decimal | None) -> float | None:
    """Decimal → float, at the payload boundary only."""
    return float(value) if value is not None else None


# --- validated inputs ------------------------------------------------------


@dataclass(frozen=True)
class Position:
    """What the user owns. Built by `parse_position`, so everything downstream
    may assume `shares > 0` and `average_cost > 0`."""

    shares: Decimal
    average_cost: Decimal

    @property
    def cost_basis(self) -> Decimal:
        """§5.1."""
        return _money(self.shares * self.average_cost)

    def as_dict(self) -> dict:
        return {
            "shares": _f(self.shares),
            "averageCost": _f(self.average_cost),
            "costBasis": _f(self.cost_basis),
        }


def parse_position(*, shares: object, average_cost: object) -> Position:
    """Validate and convert a user-supplied position (RULE-EXIT-002 / -003)."""
    share_count = to_decimal(shares, field="shares")
    cost = to_decimal(average_cost, field="averageCost")
    if share_count <= 0:
        raise PositionError("Shares must be greater than zero.")
    if cost <= 0:
        raise PositionError("Average cost must be greater than zero.")
    return Position(shares=share_count, average_cost=cost)


def parse_price(value: object, *, field: str = "price") -> Decimal:
    """Validate a market price. Zero or negative means nothing can be valued."""
    price = to_decimal(value, field=field)
    if price <= 0:
        raise PositionError(f"{field} must be greater than zero.")
    return price


# --- §5 position summary ---------------------------------------------------


@dataclass(frozen=True)
class PositionSummary:
    """§5.1-5.4 — where the position stands right now.

    Carries the price it was measured at, so every downstream calculation is
    automatically consistent with it.
    """

    shares: Decimal
    average_cost: Decimal
    current_price: Decimal
    cost_basis: Decimal
    current_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal

    @property
    def in_profit(self) -> bool:
        return self.unrealized_pnl > 0

    @property
    def status(self) -> str:
        """The §22 `pnlStatus` bucket, from the percentage rather than the dollar
        amount — 8% is 8% whether the position is $800 or $80,000, and the dollar
        size says more about the user's account than about the trade."""
        pct = self.unrealized_pnl_pct
        if pct >= 20:
            return "large-profit"
        if pct >= 5:
            return "moderate-profit"
        if pct > 0:
            return "small-profit"
        if pct == 0:
            return "break-even"
        if pct > -10:
            return "small-loss"
        return "large-loss"

    def as_dict(self) -> dict:
        return {
            "shares": _f(self.shares),
            "averageCost": _f(self.average_cost),
            "currentPrice": _f(self.current_price),
            "costBasis": _f(self.cost_basis),
            "currentValue": _f(self.current_value),
            "unrealizedPnl": _f(self.unrealized_pnl),
            "unrealizedPnlPct": _f(self.unrealized_pnl_pct),
            "inProfit": self.in_profit,
            "status": self.status,
        }


def summarize(position: Position, current_price: Decimal) -> PositionSummary:
    """§5.1-5.4. `current_price` must already have been through `parse_price`."""
    current_value = _money(position.shares * current_price)
    cost_basis = position.cost_basis
    return PositionSummary(
        shares=position.shares,
        average_cost=position.average_cost,
        current_price=current_price,
        cost_basis=cost_basis,
        current_value=current_value,
        unrealized_pnl=_money(current_value - cost_basis),
        # From the per-share prices, not the rounded dollar totals — the two
        # differ in the last decimal on large positions, and the percentage is
        # the number people sanity-check against their broker.
        unrealized_pnl_pct=_pct(
            (current_price - position.average_cost) / position.average_cost * HUNDRED
        ),
    )


# --- §7 profit giveback ----------------------------------------------------


@dataclass(frozen=True)
class GivebackLevel:
    """What happens to the position if price falls to one support level."""

    support: Decimal
    remaining_pnl: Decimal  # §5.8 — P&L still on the table down there
    giveback: Decimal  # §5.7 — profit surrendered from here
    # §5.9. Only defined on a profitable position: "42% of your profit" is
    # meaningless when there is no profit, and dividing by a negative P&L would
    # produce a confidently-signed nonsense number.
    giveback_pct_of_profit: Decimal | None
    pct_move: Decimal  # how far price has to fall to get there, in percent

    @property
    def below_cost_basis(self) -> bool:
        """This level sits under the average cost.

        Falling to it isn't "giving back profit" — it's taking a loss, and the
        percentage-of-profit figure goes past 100% to say so. Flagged rather
        than clamped, because the dollar numbers are still exactly right and
        hiding them would be worse. RULE-EXIT-011 is the rule this serves: the
        app must not phrase these levels as profit-taking.
        """
        return self.remaining_pnl < 0

    def as_dict(self) -> dict:
        return {
            "support": _f(self.support),
            "remainingPnl": _f(self.remaining_pnl),
            "giveback": _f(self.giveback),
            "givebackPctOfProfit": _f(self.giveback_pct_of_profit),
            "pctMove": _f(self.pct_move),
            "belowCostBasis": self.below_cost_basis,
        }


def giveback_at(summary: PositionSummary, support: Decimal) -> GivebackLevel:
    """§5.7-5.9 for a single support level.

    `remaining_pnl` is §5.8 by subtraction rather than by its own formula. The
    two are algebraically identical but not identical after rounding, and §7's
    card shows all three numbers together — a remaining + giveback that misses
    the headline profit by a cent reads as a bug, so the parts are made to sum.
    """
    giveback = _money((summary.current_price - support) * summary.shares)
    remaining = summary.unrealized_pnl - giveback
    return GivebackLevel(
        support=support,
        remaining_pnl=remaining,
        giveback=giveback,
        giveback_pct_of_profit=(
            _pct(giveback / summary.unrealized_pnl * HUNDRED)
            if summary.unrealized_pnl > 0
            else None
        ),
        pct_move=_pct(
            (support - summary.current_price) / summary.current_price * HUNDRED
        ),
    )


def giveback_analysis(
    summary: PositionSummary, supports: list[Decimal]
) -> list[GivebackLevel]:
    """§7 across every support level we know, nearest first.

    The spec names exactly two tiers (immediate, primary); `support_levels()`
    gives up to three near and three long-term, so this generalizes to a list
    rather than discarding levels to fit a fixed schema.

    Levels at or above the current price are dropped — "if it falls to $480"
    when the price is $472 is not a giveback scenario.
    """
    below = sorted((s for s in supports if s < summary.current_price), reverse=True)
    return [giveback_at(summary, level) for level in below]


# --- §6 hold reward/risk ---------------------------------------------------


@dataclass(frozen=True)
class HoldRewardRisk:
    """§6 — the incremental trade you make by *not* selling today."""

    target: Decimal
    support: Decimal
    upside_per_share: Decimal
    downside_per_share: Decimal
    additional_profit: Decimal  # §5.6, in dollars
    profit_giveback: Decimal  # §5.7, in dollars
    ratio: Decimal
    label: str  # strong | attractive | balanced | weak | poor

    def as_dict(self) -> dict:
        return {
            "target": _f(self.target),
            "support": _f(self.support),
            "upsidePerShare": _f(self.upside_per_share),
            "downsidePerShare": _f(self.downside_per_share),
            "additionalProfit": _f(self.additional_profit),
            "profitGiveback": _f(self.profit_giveback),
            "ratio": _f(self.ratio),
            "label": self.label,
        }


def _reward_risk_label(ratio: Decimal) -> str:
    for threshold, label in _REWARD_RISK_BANDS:
        if ratio >= threshold:
            return label
    return _REWARD_RISK_FLOOR


def hold_reward_risk(
    summary: PositionSummary, *, target: Decimal | None, support: Decimal | None
) -> HoldRewardRisk | None:
    """§6, or ``None`` when the comparison isn't defined.

    Both legs must exist and point the right way: a "target" below the current
    price is not upside, and a "support" above it is not support. None is the
    honest answer there — the alternative is a negative ratio that reads as a
    real, catastrophic number.

    Deliberately ignores average cost (§3.2). Whether the position is up 40% or
    down 40% does not change how much room is left above or below it.
    """
    if target is None or support is None:
        return None
    if target <= summary.current_price or support >= summary.current_price:
        return None

    upside = target - summary.current_price
    downside = summary.current_price - support
    ratio = _pct(upside / downside)
    return HoldRewardRisk(
        target=target,
        support=support,
        upside_per_share=_money(upside),
        downside_per_share=_money(downside),
        additional_profit=_money(upside * summary.shares),
        profit_giveback=_money(downside * summary.shares),
        ratio=ratio,
        label=_reward_risk_label(ratio),
    )


# --- §8 partial sell -------------------------------------------------------


@dataclass(frozen=True)
class PartialSell:
    """One row of the §8 calculator."""

    pct_requested: Decimal
    pct_actual: Decimal  # what the share rounding actually achieves
    shares_sold: Decimal
    shares_remaining: Decimal
    proceeds: Decimal
    realized_pnl: Decimal
    remaining_value: Decimal
    remaining_unrealized_pnl: Decimal
    # Upside left on the shares still held if the target is reached. None when
    # no target was supplied, or when the target isn't above the current price.
    additional_upside_on_remaining: Decimal | None

    @property
    def possible(self) -> bool:
        """False when whole-share rounding leaves nothing to sell — 50% of one
        share. Surfaced rather than hidden so the UI can grey the preset out
        instead of offering a plan that sells zero shares."""
        return self.shares_sold > 0

    def as_dict(self) -> dict:
        return {
            "pctRequested": _f(self.pct_requested),
            "pctActual": _f(self.pct_actual),
            "sharesSold": _f(self.shares_sold),
            "sharesRemaining": _f(self.shares_remaining),
            "proceeds": _f(self.proceeds),
            "realizedPnl": _f(self.realized_pnl),
            "remainingValue": _f(self.remaining_value),
            "remainingUnrealizedPnl": _f(self.remaining_unrealized_pnl),
            "additionalUpsideOnRemaining": _f(self.additional_upside_on_remaining),
            "possible": self.possible,
        }


def partial_sell(
    summary: PositionSummary,
    pct: object,
    *,
    target: Decimal | None = None,
    allow_fractional: bool = False,
) -> PartialSell:
    """§8 for one percentage (RULE-EXIT-012 bounds enforced here).

    Whole shares by default, rounded **down**: most cash accounts can't sell 6.6
    shares, and rounding up would sell more of the position than the user chose.
    `pct_actual` reports what the rounding really achieves, so the UI never
    labels a 30% sale as "33%".

    Realized P&L is `(price - average cost) x shares sold`. Approximate on
    purpose — real tax lots (FIFO, specific-ID) need a purchase history this
    feature doesn't collect, which is why the spec says "approximate" too.
    """
    fraction = to_decimal(pct, field="sellPct")
    if not (0 < fraction <= 100):
        raise PositionError("Sell percentage must be above 0 and at most 100.")

    raw = summary.shares * fraction / HUNDRED
    sold = raw if allow_fractional else _whole(raw)
    # Rounding only ever reduces the sale, so it can't exceed the position.
    remaining = summary.shares - sold
    gain_per_share = summary.current_price - summary.average_cost

    # The two halves are derived by subtraction from the summary's already-
    # rounded totals, not computed independently. Rounding each half on its own
    # lets them miss the whole by a cent, and this card shows the split directly
    # beneath the headline position value and P&L.
    proceeds = _money(sold * summary.current_price)
    realized = _money(gain_per_share * sold)
    return PartialSell(
        pct_requested=_pct(fraction),
        pct_actual=_pct(sold / summary.shares * HUNDRED),
        shares_sold=sold,
        shares_remaining=remaining,
        proceeds=proceeds,
        realized_pnl=realized,
        remaining_value=summary.current_value - proceeds,
        remaining_unrealized_pnl=summary.unrealized_pnl - realized,
        additional_upside_on_remaining=(
            _money((target - summary.current_price) * remaining)
            if target is not None and target > summary.current_price
            else None
        ),
    )


def partial_sell_options(
    summary: PositionSummary,
    *,
    target: Decimal | None = None,
    allow_fractional: bool = False,
    presets: tuple[int, ...] = PARTIAL_SELL_PRESETS,
) -> list[PartialSell]:
    """The §8 preset ladder: 25 / 33 / 50 / 75%."""
    return [
        partial_sell(summary, preset, target=target, allow_fractional=allow_fractional)
        for preset in presets
    ]


# --- §20 scenarios ---------------------------------------------------------


@dataclass(frozen=True)
class Scenario:
    """§20/§21 — one of bull/base/bear, with every dollar computed here.

    The AI supplies only the name, the probability, and *which* real levels bound
    the range; it never emits a price. See plan §6, "Scenarios stay grounded".
    """

    name: str
    probability: int
    price_low: Decimal
    price_high: Decimal
    value_low: Decimal
    value_high: Decimal
    pnl_low: Decimal
    pnl_high: Decimal
    change_from_current_low: Decimal
    change_from_current_high: Decimal

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "probability": self.probability,
            "priceRange": {"low": _f(self.price_low), "high": _f(self.price_high)},
            "positionValueRange": {
                "low": _f(self.value_low),
                "high": _f(self.value_high),
            },
            "pnlRange": {"low": _f(self.pnl_low), "high": _f(self.pnl_high)},
            "additionalPnlFromCurrentRange": {
                "low": _f(self.change_from_current_low),
                "high": _f(self.change_from_current_high),
            },
        }


def scenario(
    summary: PositionSummary,
    *,
    name: str,
    probability: int,
    low: Decimal,
    high: Decimal,
) -> Scenario:
    """Turn one scenario price zone into position dollars.

    `low`/`high` are ordered defensively — a model that returns them swapped
    would otherwise produce a range whose "low" sits above its "high", and the
    card reads as broken rather than as a bad guess.
    """
    lo, hi = (low, high) if low <= high else (high, low)
    return Scenario(
        name=name,
        probability=probability,
        price_low=lo,
        price_high=hi,
        value_low=_money(lo * summary.shares),
        value_high=_money(hi * summary.shares),
        pnl_low=_money((lo - summary.average_cost) * summary.shares),
        pnl_high=_money((hi - summary.average_cost) * summary.shares),
        change_from_current_low=_money((lo - summary.current_price) * summary.shares),
        change_from_current_high=_money((hi - summary.current_price) * summary.shares),
    )


def normalize_probabilities(values: list[object]) -> list[int]:
    """Force a set of scenario probabilities to whole percents summing to 100.

    Whole numbers on purpose: "30 / 45 / 25" is the honest resolution for a guess
    about the future, and 30.4% would be the false precision §3.5 forbids.

    Negatives clamp to zero, and an all-zero input splits evenly rather than
    raising — a malformed model response should cost a slightly wrong weighting,
    not the entire analysis.
    """
    if not values:
        return []
    raw = [max(ZERO, to_decimal(v, field="probability")) for v in values]
    total = sum(raw)
    if total <= 0:
        raw = [ONE] * len(raw)
        total = Decimal(len(raw))

    scaled = [v / total * HUNDRED for v in raw]
    out = [int(_whole(v)) for v in scaled]
    # Hand the rounding remainder to the largest scenario — one point moves it
    # least in relative terms.
    remainder = 100 - sum(out)
    if remainder:
        biggest = max(range(len(scaled)), key=lambda i: scaled[i])
        out[biggest] += remainder
    return out


# --- §31 cost-basis recovery ----------------------------------------------


@dataclass(frozen=True)
class CostBasisRecovery:
    """§31 — how many shares to sell to take the original stake off the table.

    Informational position sizing only. Note the spec's explicit instruction not
    to call what's left "free shares": the remaining position carries exactly the
    market risk it did before, and that framing has talked people into holding
    through losses they would otherwise have cut.
    """

    shares_needed: Decimal
    shares_remaining: Decimal
    possible: bool  # False when recovery would take the whole position
    proceeds: Decimal

    def as_dict(self) -> dict:
        return {
            "sharesNeeded": _f(self.shares_needed),
            "sharesRemaining": _f(self.shares_remaining),
            "possible": self.possible,
            "proceeds": _f(self.proceeds),
        }


def cost_basis_recovery(
    summary: PositionSummary, *, allow_fractional: bool = False
) -> CostBasisRecovery:
    """§31. Rounds **up** to a whole share by default — one share short leaves
    the stake not actually recovered, which is the only thing this view
    promises."""
    raw = summary.cost_basis / summary.current_price
    if allow_fractional:
        needed = raw
    else:
        needed = _whole(raw)
        if needed < raw:  # never round down past full recovery
            needed += ONE

    return CostBasisRecovery(
        shares_needed=needed,
        shares_remaining=max(ZERO, summary.shares - needed),
        possible=needed < summary.shares,
        proceeds=_money(min(needed, summary.shares) * summary.current_price),
    )
