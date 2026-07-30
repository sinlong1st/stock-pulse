"""Watchlist commands: show, add (/watch), and remove (/unwatch) tickers."""

from collections.abc import Awaitable, Callable

from app.commands.symbols import resolve_symbol
from app.watchlist import (
    add_ticker,
    get_watchlist_config,
    remove_ticker,
    watchlist_file_is_empty,
)

Resolver = Callable[[str], Awaitable[tuple[str, str] | None]]


def render_watchlist(*, language: str = "English") -> str:
    """Format the current watchlist for a Telegram reply."""
    vi = language.strip().lower() == "vietnamese"
    wl = get_watchlist_config()
    if not wl.tickers:
        return "📋 Danh sách theo dõi đang trống." if vi else "📋 Your watchlist is empty."

    header = (
        f"📋 Danh sách theo dõi ({len(wl.tickers)}):"
        if vi
        else f"📋 Watchlist ({len(wl.tickers)}):"
    )
    lines = [header]
    for ticker in wl.tickers:
        names = wl.aliases.get(ticker) or []
        alias = f" — {names[0]}" if names else ""
        lines.append(f"• {ticker}{alias}")
    return "\n".join(lines)


async def cmd_watch(
    args: str,
    *,
    language: str = "English",
    resolver: Resolver | None = None,
    path: str | None = None,
) -> str:
    """Add a stock to the watchlist, resolving a name/typo to a ticker."""
    vi = language.strip().lower() == "vietnamese"
    query = args.strip()
    if not query:
        return (
            "Dùng: /watch <tên hoặc mã>, vd /watch tesla"
            if vi
            else "Usage: /watch <name or ticker>, e.g. /watch tesla"
        )

    resolve = resolver or resolve_symbol
    result = await resolve(query)
    if result is None:
        return (
            f"Không tìm thấy cổ phiếu cho '{query}'. Thử nhập mã chứng khoán."
            if vi
            else f"Couldn't find a stock for '{query}'. Try the ticker symbol."
        )
    symbol, name = result
    added = add_ticker(symbol, [name] if name and name != symbol else [], path=path)
    if not added:
        return f"ℹ️ Đang theo dõi {symbol} rồi." if vi else f"ℹ️ Already watching {symbol}."
    return f"✅ Đã thêm {symbol} ({name})." if vi else f"✅ Added {symbol} ({name})."


async def cmd_unwatch(args: str, *, language: str = "English", path: str | None = None) -> str:
    """Remove a stock from the watchlist."""
    vi = language.strip().lower() == "vietnamese"
    symbol = args.strip().upper()
    if not symbol:
        return (
            "Dùng: /unwatch <mã>, vd /unwatch tsla"
            if vi
            else "Usage: /unwatch <ticker>, e.g. /unwatch tsla"
        )

    removed = remove_ticker(symbol, path=path)
    if not removed:
        return (
            f"'{symbol}' không có trong danh sách."
            if vi
            else f"'{symbol}' isn't on your watchlist."
        )
    reply = f"🗑️ Đã bỏ {symbol}." if vi else f"🗑️ Removed {symbol}."
    if watchlist_file_is_empty(path):
        reply += (
            " ⚠️ Danh sách trống — sẽ dùng mặc định cho tới khi bạn thêm lại."
            if vi
            else " ⚠️ Watchlist is now empty — falling back to defaults until you add one."
        )
    return reply
