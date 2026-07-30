"""Telegram command handlers (the manage-from-your-phone commands).

Each handler is ``async (args: str) -> str | None`` and is registered with the
`TelegramListener` router. Read-only commands (`/watchlist`, `/help`) return
their reply text; `/report` sends its own messages and returns None.
"""

from app.commands.help import render_help
from app.commands.language import cmd_language
from app.commands.watchlist_cmds import cmd_unwatch, cmd_watch, render_watchlist
from app.prefs import resolve_language

__all__ = [
    "render_help",
    "render_watchlist",
    "cmd_watch",
    "cmd_unwatch",
    "cmd_language",
    "build_command_handlers",
]


def build_command_handlers(settings, *, report_handler):
    """Assemble the command registry: the /report handler (passed in, since it
    owns the Telegram notifier) plus the built-in watchlist/language commands.

    The reply language is resolved live (not captured once), so a `/language`
    switch is reflected by the very next command."""
    handlers: dict = {settings.briefing_command: report_handler}

    def _lang() -> str:
        return resolve_language(settings)

    async def _watchlist(_args: str) -> str:
        return render_watchlist(language=_lang())

    async def _watch(args: str) -> str:
        return await cmd_watch(args, language=_lang())

    async def _unwatch(args: str) -> str:
        return await cmd_unwatch(args, language=_lang())

    async def _language(args: str) -> str:
        return await cmd_language(args, language=_lang(), path=settings.prefs_file)

    async def _help(_args: str) -> str:
        return render_help(sorted(handlers), language=_lang())

    handlers["/watchlist"] = _watchlist
    handlers["/watch"] = _watch
    handlers["/unwatch"] = _unwatch
    handlers["/language"] = _language
    handlers["/help"] = _help
    return handlers
