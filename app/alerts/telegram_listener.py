"""Inbound Telegram command listener (a small command router).

Everything else in StockPulse only *sends* Telegram messages; this is the one
piece that *receives* them. It long-polls the Bot API's ``getUpdates`` (no
public webhook needed, so it works from a local machine) and routes the owner's
commands (`/report`, `/watchlist`, `/watch`, ...) to registered handlers.

Locked to a single authorized chat id: a stray/abusive message from anywhere
else is ignored so it can never spend budget or edit config. Updates are
processed sequentially, and the startup backlog is skipped so an old command
sitting in the queue doesn't fire on boot.

A handler has signature ``async (args: str) -> str | None``: it returns the
reply text to send back, or ``None`` if it sends its own messages (as `/report`
does — an ack, then the full brief).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx

from app.alerts.telegram import NotifierError
from app.config import Settings, get_settings

logger = logging.getLogger("stockpulse.alerts.telegram_listener")

CommandHandler = Callable[[str], Awaitable[str | None]]


def _command_token(text: str) -> str:
    """First token of a message, without a bot @suffix, lower-cased.

    "/report@MyBot now" -> "/report".
    """
    if not text:
        return ""
    token = text.strip().split(maxsplit=1)[0]
    return token.split("@", 1)[0].lower()


def _split_command(text: str) -> tuple[str, str]:
    """Split a message into (command_token, args). "/watch tesla" -> ("/watch", "tesla")."""
    cmd = _command_token(text)
    parts = text.strip().split(maxsplit=1)
    args = parts[1].strip() if len(parts) > 1 else ""
    return cmd, args


class TelegramListener:
    """Long-polls Telegram and routes owner commands to registered handlers."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        *,
        handlers: dict[str, CommandHandler],
        poll_timeout: int = 25,
        timeout: float = 40.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not bot_token or not chat_id:
            raise NotifierError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set.")
        self.bot_token = bot_token
        self.chat_id = str(chat_id)
        # Normalize keys: lower-cased, leading slash.
        self.handlers = {
            (k.lower() if k.startswith("/") else f"/{k.lower()}"): v for k, v in handlers.items()
        }
        self.poll_timeout = poll_timeout
        self.timeout = timeout
        self._transport = transport
        self._offset: int | None = None
        self._base = f"https://api.telegram.org/bot{bot_token}"

    def _owner_command(self, update: dict) -> tuple[str, str] | None:
        """Return (command, args) if this update is a known command from the owner."""
        message = update.get("message") or update.get("edited_message")
        if not isinstance(message, dict):
            return None
        chat = message.get("chat") or {}
        if str(chat.get("id")) != self.chat_id:
            return None  # not the owner — ignore
        cmd, args = _split_command(message.get("text") or "")
        if cmd not in self.handlers:
            return None
        return cmd, args

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
            parsed = self._owner_command(update)
            if parsed is None:
                continue
            cmd, args = parsed
            try:
                reply = await self.handlers[cmd](args)
                if reply:
                    await self._send(reply)
                handled += 1
            except Exception:  # a bad handler must not kill the poll loop
                logger.exception("Error handling command %s", cmd)
        return handled

    async def _send(self, text: str) -> None:
        """Send a reply to the owner chat (handler-returned text)."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
                resp = await client.post(
                    f"{self._base}/sendMessage",
                    json={"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True},
                )
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Failed to send command reply: %s", exc)

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
        logger.info(
            "Telegram command listener started (chat=%s, commands=%s).",
            self.chat_id,
            ", ".join(sorted(self.handlers)),
        )
        while not stop_event.is_set():
            try:
                await self.poll_once()
            except (httpx.HTTPError, NotifierError) as exc:
                logger.warning("Telegram poll failed: %s; retrying shortly.", exc)
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=5.0)
                except TimeoutError:
                    pass
        logger.info("Telegram listener stopped.")


def build_command_listener(
    settings: Settings | None = None, *, handlers: dict[str, CommandHandler]
) -> TelegramListener:
    """Construct the command listener from settings. Raises if creds are missing."""
    settings = settings or get_settings()
    return TelegramListener(
        settings.telegram_bot_token,
        settings.telegram_chat_id,
        handlers=handlers,
    )
