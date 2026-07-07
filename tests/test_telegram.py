"""Tests for alert formatting and Telegram delivery (Phase 6).

Telegram's API is never called for real: a httpx MockTransport returns
canned responses.
"""

from datetime import UTC, datetime

import httpx
import pytest

from app.alerts.formatter import format_alert_message
from app.alerts.telegram import NotifierError, TelegramNotifier
from app.models.article import NewsArticle
from app.models.classification import ClassificationResult


def _article() -> NewsArticle:
    return NewsArticle(
        source="Yahoo Finance",
        title="Fed signals rate cuts may be delayed",
        summary="Powell comments push yields higher.",
        url="https://example.com/fed",
        collected_at=datetime.now(tz=UTC),
        content_hash="h" * 64,
    )


def _classification() -> ClassificationResult:
    return ClassificationResult(
        is_market_relevant=True,
        importance="HIGH",
        category="MACRO",
        related_tickers=["QQQ", "NVDA"],
        summary="Fed may delay cuts.",
        why_it_matters="Higher-for-longer rates pressure tech.",
        should_alert=True,
        confidence=0.9,
    )


def test_format_alert_message_contains_key_fields() -> None:
    message = format_alert_message(_article(), _classification())
    assert "HIGH MACRO NEWS" in message
    assert "Fed signals rate cuts may be delayed" in message
    assert "Why it matters:" in message
    assert "QQQ, NVDA" in message
    assert "Yahoo Finance" in message
    assert "https://example.com/fed" in message


async def test_telegram_send_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/bottoken/sendMessage"
        body = request.read().decode()
        assert "chat-1" in body
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    notifier = TelegramNotifier("token", "chat-1", transport=httpx.MockTransport(handler))
    await notifier.send("hello")  # should not raise


async def test_telegram_send_api_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "description": "bad chat"})

    notifier = TelegramNotifier("token", "chat-1", transport=httpx.MockTransport(handler))
    with pytest.raises(NotifierError):
        await notifier.send("hello")


async def test_telegram_http_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    notifier = TelegramNotifier("token", "chat-1", transport=httpx.MockTransport(handler))
    with pytest.raises(NotifierError):
        await notifier.send("hello")


def test_telegram_requires_credentials() -> None:
    with pytest.raises(NotifierError):
        TelegramNotifier("", "")
