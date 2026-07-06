"""Alert decision engine (pipeline Step 6).

The application — not the AI — owns the final alert decision. The AI's
`should_alert` is only a recommendation; this policy decides based on the
importance level meeting a configurable threshold and the article being
market-relevant, then maps importance to notification channels.
"""

from dataclasses import dataclass, field
from functools import lru_cache

from app.alerts.constants import CHANNEL_TELEGRAM
from app.config import get_settings
from app.models.classification import ClassificationResult

# Ordering so thresholds can be compared numerically.
IMPORTANCE_ORDER: dict[str, int] = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

# MVP: every alert-worthy level goes to Telegram. Future levels can add
# push/phone channels here without touching the decision logic.
DEFAULT_CHANNELS_BY_IMPORTANCE: dict[str, list[str]] = {
    "MEDIUM": [CHANNEL_TELEGRAM],
    "HIGH": [CHANNEL_TELEGRAM],
    "CRITICAL": [CHANNEL_TELEGRAM],
}


@dataclass
class AlertDecision:
    """The application's final decision for one classified article."""

    should_alert: bool
    importance: str
    channels: list[str] = field(default_factory=list)
    reason: str = ""


class AlertPolicy:
    """Decide whether and where to alert, from a classification result."""

    def __init__(
        self,
        min_importance: str = "MEDIUM",
        channels_by_importance: dict[str, list[str]] | None = None,
    ) -> None:
        self.min_importance = min_importance.upper()
        self.min_rank = IMPORTANCE_ORDER.get(self.min_importance, 1)
        self.channels_by_importance = channels_by_importance or DEFAULT_CHANNELS_BY_IMPORTANCE

    def decide(self, classification: ClassificationResult) -> AlertDecision:
        importance = classification.importance
        rank = IMPORTANCE_ORDER.get(importance, 0)

        if not classification.is_market_relevant:
            return AlertDecision(False, importance, [], "not market-relevant")
        if rank < self.min_rank:
            return AlertDecision(
                False, importance, [], f"{importance} below threshold {self.min_importance}"
            )

        channels = list(self.channels_by_importance.get(importance, [CHANNEL_TELEGRAM]))
        return AlertDecision(
            True, importance, channels, f"{importance} meets threshold {self.min_importance}"
        )


@lru_cache
def get_alert_policy() -> AlertPolicy:
    """Return a process-wide AlertPolicy built from settings."""
    return AlertPolicy(min_importance=get_settings().alert_min_importance)
