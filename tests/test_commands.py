"""Tests for the Telegram command handlers (/watchlist, /help, router build)."""

from app.commands import build_command_handlers, render_help, render_watchlist
from app.config import Settings
from app.watchlist import WatchlistConfig

WL = WatchlistConfig(tickers=("NVDA", "MSFT"), aliases={"NVDA": ["Nvidia"], "MSFT": ["Microsoft"]})


def test_render_watchlist(monkeypatch) -> None:
    from app.commands import watchlist_cmds

    monkeypatch.setattr(watchlist_cmds, "get_watchlist_config", lambda: WL)
    text = render_watchlist(language="English")
    assert "Watchlist (2)" in text
    assert "NVDA — Nvidia" in text
    assert "MSFT — Microsoft" in text


def test_render_watchlist_vietnamese(monkeypatch) -> None:
    from app.commands import watchlist_cmds

    monkeypatch.setattr(watchlist_cmds, "get_watchlist_config", lambda: WL)
    text = render_watchlist(language="Vietnamese")
    assert "Danh sách theo dõi" in text


def test_render_watchlist_empty(monkeypatch) -> None:
    from app.commands import watchlist_cmds

    empty = WatchlistConfig(tickers=(), aliases={})
    monkeypatch.setattr(watchlist_cmds, "get_watchlist_config", lambda: empty)
    assert "empty" in render_watchlist(language="English").lower()


def test_render_help_lists_given_commands() -> None:
    text = render_help(["/report", "/watchlist", "/help"], language="English")
    assert "/report" in text and "/watchlist" in text and "/help" in text
    assert "Market report" in text


async def test_build_command_handlers_wires_report_and_readonly() -> None:
    called = {"report_args": None}

    async def report_handler(args):
        called["report_args"] = args
        return None

    settings = Settings(_env_file=None, briefing_command="/report", output_language="English")
    handlers = build_command_handlers(settings, report_handler=report_handler)

    assert {"/report", "/watchlist", "/help"} <= set(handlers)
    # /report is the passed-in handler
    await handlers["/report"]("wdc")
    assert called["report_args"] == "wdc"
    # /help reflects the registered commands
    help_text = await handlers["/help"]("")
    assert "/watchlist" in help_text
