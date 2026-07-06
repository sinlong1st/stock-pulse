"""Tests for the alert decision engine (Phase 5)."""

from app.alerts.constants import CHANNEL_TELEGRAM
from app.alerts.policy import AlertPolicy
from app.models.classification import ClassificationResult


def _result(importance: str, *, relevant: bool = True, ai_alert: bool = True) -> ClassificationResult:
    return ClassificationResult(
        is_market_relevant=relevant,
        importance=importance,
        category="MACRO",
        related_tickers=[],
        summary="s",
        why_it_matters="w",
        should_alert=ai_alert,
        confidence=0.8,
    )


def test_low_importance_does_not_alert() -> None:
    decision = AlertPolicy().decide(_result("LOW"))
    assert decision.should_alert is False
    assert decision.channels == []


def test_medium_high_critical_alert_to_telegram() -> None:
    policy = AlertPolicy()
    for importance in ("MEDIUM", "HIGH", "CRITICAL"):
        decision = policy.decide(_result(importance))
        assert decision.should_alert is True
        assert decision.channels == [CHANNEL_TELEGRAM]


def test_not_market_relevant_never_alerts_even_if_high() -> None:
    decision = AlertPolicy().decide(_result("HIGH", relevant=False))
    assert decision.should_alert is False
    assert "not market-relevant" in decision.reason


def test_app_owns_decision_ignores_ai_recommendation() -> None:
    # AI says alert, but LOW is below threshold -> app says no.
    assert AlertPolicy().decide(_result("LOW", ai_alert=True)).should_alert is False
    # AI says don't alert, but HIGH meets threshold -> app says yes.
    assert AlertPolicy().decide(_result("HIGH", ai_alert=False)).should_alert is True


def test_threshold_is_configurable() -> None:
    policy = AlertPolicy(min_importance="HIGH")
    assert policy.decide(_result("MEDIUM")).should_alert is False
    assert policy.decide(_result("HIGH")).should_alert is True
