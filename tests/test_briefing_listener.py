"""Tests for the inbound Telegram /report listener (Briefing plan, step F).

The Telegram API is never called for real: a httpx MockTransport serves canned
getUpdates responses, and process_updates is exercised directly with update
dicts.
"""

import httpx
import pytest

from app.alerts.telegram import NotifierError
from app.alerts.telegram_listener import TelegramListener, _command_token

OWNER = "12345"
OTHER = "99999"


def _update(update_id: int, chat_id: str, text: str) -> dict:
    return {
        "update_id": update_id,
        "message": {"message_id": update_id, "chat": {"id": int(chat_id)}, "text": text},
    }


def _listener(handler=None, *, on_command=None, command="/report") -> TelegramListener:
    transport = httpx.MockTransport(handler) if handler else None
    return TelegramListener(
        "bot-token", OWNER, command=command, on_command=on_command, transport=transport
    )


def test_command_token_strips_bot_suffix_and_args() -> None:
    assert _command_token("/report@StockPulseBot now") == "/report"
    assert _command_token("/REPORT") == "/report"
    assert _command_token("hello") == "hello"
    assert _command_token("") == ""


async def test_only_owner_command_triggers_handler() -> None:
    seen: list[str] = []

    async def on_command(chat_id, text):
        seen.append(text)

    listener = _listener(on_command=on_command)
    handled = await listener.process_updates(
        [
            _update(1, OWNER, "/report"),  # owner -> handled
            _update(2, OTHER, "/report"),  # different chat -> ignored
            _update(3, OWNER, "hello"),  # not the command -> ignored
            _update(4, OWNER, "/report@StockPulseBot"),  # bot suffix -> handled
        ]
    )
    assert handled == 2
    assert seen == ["/report", "/report@StockPulseBot"]
    assert listener._offset == 5  # advanced past every update


async def test_handler_error_does_not_break_loop() -> None:
    async def boom(chat_id, text):
        raise RuntimeError("handler failed")

    listener = _listener(on_command=boom)
    handled = await listener.process_updates([_update(1, OWNER, "/report")])
    assert handled == 0
    assert listener._offset == 2  # still advanced


async def test_poll_once_fetches_and_handles() -> None:
    calls = {"n": 0}

    async def on_command(chat_id, text):
        calls["n"] += 1

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"ok": True, "result": [_update(7, OWNER, "/report")]}
        )

    listener = _listener(handler, on_command=on_command)
    handled = await listener.poll_once()
    assert handled == 1
    assert calls["n"] == 1
    assert listener._offset == 8


async def test_prime_skips_backlog_without_handling() -> None:
    async def on_command(chat_id, text):
        raise AssertionError("prime must not handle commands")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"ok": True, "result": [_update(10, OWNER, "/report"), _update(11, OWNER, "/report")]},
        )

    listener = _listener(handler, on_command=on_command)
    await listener.prime()
    assert listener._offset == 12  # advanced past backlog, nothing handled


async def test_get_updates_raises_on_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "description": "boom"})

    listener = _listener(handler)
    with pytest.raises(NotifierError):
        await listener.poll_once()


def test_missing_credentials_raise() -> None:
    with pytest.raises(NotifierError):
        TelegramListener("", OWNER)
