"""Tests for the inbound Telegram command router.

The Telegram API is never called for real: a httpx MockTransport serves canned
getUpdates/sendMessage responses, and process_updates is exercised directly with
update dicts.
"""

import httpx
import pytest

from app.alerts.telegram import NotifierError
from app.alerts.telegram_listener import TelegramListener, _command_token, _split_command

OWNER = "12345"
OTHER = "99999"


def _update(update_id: int, chat_id: str, text: str) -> dict:
    return {
        "update_id": update_id,
        "message": {"message_id": update_id, "chat": {"id": int(chat_id)}, "text": text},
    }


def _listener(handlers, handler_fn=None, *, transport=None) -> TelegramListener:
    return TelegramListener("bot-token", OWNER, handlers=handlers, transport=transport)


def test_command_token_strips_bot_suffix_and_args() -> None:
    assert _command_token("/report@StockPulseBot now") == "/report"
    assert _command_token("/REPORT") == "/report"
    assert _command_token("hello") == "hello"
    assert _command_token("") == ""


def test_split_command() -> None:
    assert _split_command("/watch tesla") == ("/watch", "tesla")
    assert _split_command("/report@Bot wdc now") == ("/report", "wdc now")
    assert _split_command("/watchlist") == ("/watchlist", "")


async def test_routes_to_the_right_handler() -> None:
    seen: list[str] = []

    async def report(args):
        seen.append(f"report:{args}")
        return None

    async def watchlist(args):
        seen.append("watchlist")
        return None

    listener = _listener({"/report": report, "/watchlist": watchlist})
    handled = await listener.process_updates(
        [
            _update(1, OWNER, "/report wdc"),  # -> report handler with args
            _update(2, OWNER, "/watchlist"),  # -> watchlist handler
            _update(3, OTHER, "/watchlist"),  # different chat -> ignored
            _update(4, OWNER, "/unknown"),  # no handler -> ignored
        ]
    )
    assert handled == 2
    assert seen == ["report:wdc", "watchlist"]
    assert listener._offset == 5  # advanced past every update


async def test_reply_text_is_sent_back() -> None:
    calls = {"sent": None}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getUpdates"):
            updates = [_update(7, OWNER, "/watchlist")]
            return httpx.Response(200, json={"ok": True, "result": updates})
        # sendMessage
        import json

        calls["sent"] = json.loads(request.content)["text"]
        return httpx.Response(200, json={"ok": True})

    async def watchlist(args):
        return "📋 Watchlist (1): NVDA"

    listener = _listener({"/watchlist": watchlist}, transport=httpx.MockTransport(handler))
    handled = await listener.poll_once()
    assert handled == 1
    assert calls["sent"] == "📋 Watchlist (1): NVDA"


async def test_handler_error_does_not_break_loop() -> None:
    async def boom(args):
        raise RuntimeError("handler failed")

    listener = _listener({"/report": boom})
    handled = await listener.process_updates([_update(1, OWNER, "/report")])
    assert handled == 0
    assert listener._offset == 2  # still advanced


async def test_prime_skips_backlog_without_handling() -> None:
    async def report(args):
        raise AssertionError("prime must not handle commands")

    def handler(request: httpx.Request) -> httpx.Response:
        backlog = [_update(10, OWNER, "/report"), _update(11, OWNER, "/report")]
        return httpx.Response(200, json={"ok": True, "result": backlog})

    listener = _listener({"/report": report}, transport=httpx.MockTransport(handler))
    await listener.prime()
    assert listener._offset == 12  # advanced past backlog, nothing handled


async def test_get_updates_raises_on_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "description": "boom"})

    listener = _listener({"/report": lambda a: None}, transport=httpx.MockTransport(handler))
    with pytest.raises(NotifierError):
        await listener.poll_once()


def test_missing_credentials_raise() -> None:
    with pytest.raises(NotifierError):
        TelegramListener("", OWNER, handlers={})


def test_handler_keys_are_normalized() -> None:
    async def h(args):
        return None

    listener = TelegramListener("t", OWNER, handlers={"watch": h, "/REPORT": h})
    assert set(listener.handlers) == {"/watch", "/report"}
