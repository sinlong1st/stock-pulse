"""Inbound Telegram listener for the on-demand `/report` command.

Everything else in StockPulse only *sends* Telegram messages; this is the one
piece that *receives* them. It long-polls the Bot API's ``getUpdates`` (no
public webhook needed, so it works from a local machine) and, when the owner
sends the command, invokes a callback — the briefing job.

Locked to a single authorized chat id: a stray/abusive message from anywhere
else is ignored so it can never spend OpenAI budget. Updates are processed
sequentially (one report at a time), and the startup backlog is skipped so an
old `/report` sitting in the queue doesn't fire on boot.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx

from app.alerts.telegram import NotifierError
from app.config import Settings, get_settings

logger = logging.getLogger("stockpulse.alerts.telegram_listener")

CommandHandler = Callable[[str, str], Awaitable[None]]


def _command_token(text: str) -> str:
    """First token of a message, without a bot @suffix, lower-cased.

    "/report@MyBot now" -> "/report".
    """
    if not text:
        return ""
    token = text.strip().split(maxsplit=1)[0]
    return token.split("@", 1)[0].lower()


class TelegramListener:
    """Long-polls Telegram for the `/report` command from the owner chat."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        *,
        command: str = "/report",
        on_command: CommandHandler | None = None,
        poll_timeout: int = 25,
        timeout: float = 40.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not bot_token or not chat_id:
            raise NotifierError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set.")
        self.bot_token = bot_token
        self.chat_id = str(chat_id)
        self.command = command.lower() if command.startswith("/") else f"/{command.lower()}"
        self.on_command = on_command
        self.poll_timeout = poll_timeout
        self.timeout = timeout
        self._transport = transport
        self._offset: int | None = None
        self._base = f"https://api.telegram.org/bot{bot_token}"

    def _authorized_command(self, update: dict) -> str | None:
        """Return the message text if this update is the command from the owner."""
        message = update.get("message") or update.get("edited_message")
        if not isinstance(message, dict):
            return None
        chat = message.get("chat") or {}
        if str(chat.get("id")) != self.chat_id:
            return None  # not the owner — ignore
        text = message.get("text") or ""
        if _command_token(text) != self.command:
            return None
        return text

    async def process_updates(self, updates: list[dict]) -> int:
        """Handle a batch of updates; returns how many commands were run.

        Always advances the offset past every update (even ignored ones) so
        they are not re-fetched.
        """
        handled = 0
        for update in updates:
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                self._offset = update_id + 1
            text = self._authorized_command(update)
            if text is None:
                continue
            if self.on_command is None:
                continue
            try:
                await self.on_command(self.chat_id, text)
                handled += 1
            except Exception:  # a bad handler must not kill the poll loop
                logger.exception("Error handling /report command")
        return handled

    async def _get_updates(self, *, long_poll: bool) -> list[dict]:
        params: dict = {"timeout": self.poll_timeout if long_poll else 0}
        if self._offset is not None:
            params["offset"] = self._offset
        async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
            response = await client.get(f"{self._base}/getUpdates", params=params)
            response.raise_for_status()
            data = response.json()
        if not data.get("ok", False):
            raise NotifierError(f"Telegram getUpdates error: {data}")
        return data.get("result", [])

    async def prime(self) -> None:
        """Skip any backlog so an old queued command doesn't fire on boot."""
        try:
            updates = await self._get_updates(long_poll=False)
        except (httpx.HTTPError, NotifierError):
            logger.warning("Could not prime Telegram listener; starting from scratch.")
            return
        for update in updates:
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                self._offset = update_id + 1

    async def poll_once(self) -> int:
        """One long-poll + process cycle. Returns commands handled."""
        updates = await self._get_updates(long_poll=True)
        return await self.process_updates(updates)

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        """Poll until ``stop_event`` is set. Transient errors back off briefly."""
        await self.prime()
        logger.info("Telegram %s listener started (chat=%s).", self.command, self.chat_id)
        while not stop_event.is_set():
            try:
                await self.poll_once()
            except (httpx.HTTPError, NotifierError) as exc:
                logger.warning("Telegram poll failed: %s; retrying shortly.", exc)
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
        logger.info("Telegram listener stopped.")


def build_report_listener(
    settings: Settings | None = None, *, on_command: CommandHandler | None = None
) -> TelegramListener:
    """Construct the /report listener from settings. Raises if creds are missing."""
    settings = settings or get_settings()
    return TelegramListener(
        settings.telegram_bot_token,
        settings.telegram_chat_id,
        command=settings.briefing_command,
        on_command=on_command,
    )
