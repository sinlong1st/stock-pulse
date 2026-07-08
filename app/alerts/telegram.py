"""Telegram notification channel.

Isolated behind a `Notifier` interface so more channels (push, phone) can
be added later without touching the delivery router.
"""

import logging
from abc import ABC, abstractmethod

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger("stockpulse.alerts.telegram")


class NotifierError(Exception):
    """Raised when a notification cannot be delivered."""


class Notifier(ABC):
    """Sends a plain-text message over some channel."""

    @abstractmethod
    async def send(self, text: str) -> None:
        raise NotImplementedError


class TelegramNotifier(Notifier):
    """Send messages via the Telegram Bot API."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        *,
        disable_preview: bool = True,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not bot_token or not chat_id:
            raise NotifierError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set.")
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.disable_preview = disable_preview
        self.timeout = timeout
        self._transport = transport

    async def send(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
                response = await client.post(
                    url,
                    json={
                        "chat_id": self.chat_id,
                        "text": text,
                        "disable_web_page_preview": self.disable_preview,
                    },
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise NotifierError(f"Telegram request failed: {exc}") from exc

        if not data.get("ok", False):
            raise NotifierError(f"Telegram API error: {data}")


def build_telegram_notifier(settings: Settings | None = None) -> TelegramNotifier:
    """Construct a Telegram notifier from settings. Raises if creds are missing."""
    settings = settings or get_settings()
    return TelegramNotifier(
        settings.telegram_bot_token,
        settings.telegram_chat_id,
        disable_preview=not settings.alert_link_preview,
    )
