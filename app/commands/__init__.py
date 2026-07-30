"""Telegram command handlers (the manage-from-your-phone commands).

Each handler is ``async (args: str) -> str | None`` and is registered with the
`TelegramListener` router. Read-only commands (`/watchlist`, `/help`) return
their reply text; `/report` sends its own messages and returns None.
"""

from app.commands.help import render_help
from app.commands.watchlist_cmds import cmd_unwatch, cmd_watch, render_watchlist

__all__ = [
    "render_help",
    "render_watchlist",
    "cmd_watch",
    "cmd_unwatch",
    "build_command_handlers",
]


def build_command_handlers(settings, *, report_handler):
    """Assemble the command registry: the /report handler (passed in, since it
    owns the Telegram notifier) plus the built-in watchlist commands."""
    lang = settings.output_language
    handlers: dict = {settings.briefing_command: report_handler}

    async def _watchlist(_args: str) -> str:
        return render_watchlist(language=lang)

    async def _watch(args: str) -> str:
        return await cmd_watch(args, language=lang)

    async def _unwatch(args: str) -> str:
        return await cmd_unwatch(args, language=lang)

    async def _help(_args: str) -> str:
        return render_help(sorted(handlers), language=lang)

    handlers["/watchlist"] = _watchlist
    handlers["/watch"] = _watch
    handlers["/unwatch"] = _unwatch
    handlers["/help"] = _help
    return handlers
