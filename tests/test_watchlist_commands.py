"""Tests for /watch and /unwatch: symbol resolution + watchlist mutation."""

import json

import httpx

from app.commands.symbols import resolve_symbol
from app.commands.watchlist_cmds import cmd_unwatch, cmd_watch
from app.config import Settings
from app.watchlist import (
    add_ticker,
    load_watchlist,
    remove_ticker,
    watchlist_file_is_empty,
)


def _seed(path, data: dict) -> str:
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


# --- watchlist mutation ----------------------------------------------------


def test_add_and_remove_roundtrip(tmp_path) -> None:
    wl = _seed(tmp_path / "watchlist.json", {"NVDA": ["Nvidia"]})

    assert add_ticker("TSLA", ["Tesla, Inc."], path=wl) is True
    cfg = load_watchlist(wl)
    assert "TSLA" in cfg.tickers and cfg.aliases["TSLA"] == ["Tesla, Inc."]

    assert add_ticker("tsla", path=wl) is False  # already present (case-insensitive)

    assert remove_ticker("TSLA", path=wl) is True
    assert "TSLA" not in load_watchlist(wl).tickers
    assert remove_ticker("TSLA", path=wl) is False  # gone


def test_watchlist_file_is_empty(tmp_path) -> None:
    empty = _seed(tmp_path / "e.json", {})
    full = _seed(tmp_path / "f.json", {"NVDA": []})
    assert watchlist_file_is_empty(empty) is True
    assert watchlist_file_is_empty(full) is False


# --- symbol resolution -----------------------------------------------------


def _search_response(quotes: list[dict]) -> httpx.Response:
    return httpx.Response(200, json={"quotes": quotes})


async def test_resolve_symbol_picks_top_equity() -> None:
    quotes = [
        {"quoteType": "INDEX", "symbol": "^X"},
        {"quoteType": "EQUITY", "symbol": "TSLA", "shortname": "Tesla, Inc."},
    ]
    result = await resolve_symbol(
        "tesla",
        settings=Settings(_env_file=None),
        transport=httpx.MockTransport(lambda r: _search_response(quotes)),
    )
    assert result == ("TSLA", "Tesla, Inc.")


async def test_resolve_symbol_none_when_no_equity() -> None:
    result = await resolve_symbol(
        "zzzz",
        settings=Settings(_env_file=None),
        transport=httpx.MockTransport(lambda r: _search_response([])),
    )
    assert result is None


# --- /watch ----------------------------------------------------------------


async def _fake_resolver(query):
    return ("TSLA", "Tesla, Inc.")


async def test_cmd_watch_adds(tmp_path) -> None:
    wl = _seed(tmp_path / "watchlist.json", {"NVDA": ["Nvidia"]})
    reply = await cmd_watch("tesla", resolver=_fake_resolver, path=wl)
    assert "Added TSLA" in reply
    assert "TSLA" in load_watchlist(wl).tickers


async def test_cmd_watch_already_watching(tmp_path) -> None:
    wl = _seed(tmp_path / "watchlist.json", {"TSLA": ["Tesla"]})
    reply = await cmd_watch("tesla", resolver=_fake_resolver, path=wl)
    assert "Already watching" in reply


async def test_cmd_watch_no_match(tmp_path) -> None:
    async def none_resolver(q):
        return None

    wl = _seed(tmp_path / "watchlist.json", {"NVDA": []})
    reply = await cmd_watch("zzz", resolver=none_resolver, path=wl)
    assert "Couldn't find" in reply


async def test_cmd_watch_usage_on_empty() -> None:
    assert "Usage" in await cmd_watch("   ", resolver=_fake_resolver)


# --- /unwatch --------------------------------------------------------------


async def test_cmd_unwatch_removes(tmp_path) -> None:
    wl = _seed(tmp_path / "watchlist.json", {"NVDA": ["Nvidia"], "TSLA": ["Tesla"]})
    reply = await cmd_unwatch("tsla", path=wl)
    assert "Removed TSLA" in reply
    assert "TSLA" not in load_watchlist(wl).tickers


async def test_cmd_unwatch_not_present(tmp_path) -> None:
    wl = _seed(tmp_path / "watchlist.json", {"NVDA": []})
    reply = await cmd_unwatch("tsla", path=wl)
    assert "isn't on your watchlist" in reply


async def test_cmd_unwatch_last_warns_empty(tmp_path) -> None:
    wl = _seed(tmp_path / "watchlist.json", {"NVDA": []})
    reply = await cmd_unwatch("nvda", path=wl)
    assert "Removed NVDA" in reply
    assert "empty" in reply.lower()


def test_registry_includes_watch_commands() -> None:
    from app.commands import build_command_handlers

    async def report_handler(args):
        return None

    handlers = build_command_handlers(
        Settings(_env_file=None, briefing_command="/report"), report_handler=report_handler
    )
    assert {"/watch", "/unwatch", "/watchlist", "/help", "/report"} <= set(handlers)
