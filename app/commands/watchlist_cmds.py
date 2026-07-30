"""Watchlist commands: show (and later add/remove) the watched tickers."""

from app.watchlist import get_watchlist_config


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
