"""The /help command: list the available commands."""

# command -> (Vietnamese description, English description)
_DESCRIPTIONS = {
    "/report": (
        "Bản tin thị trường (thêm mã để xem 1 cổ phiếu, vd /report wdc)",
        "Market report (add a ticker for one stock, e.g. /report wdc)",
    ),
    "/watchlist": ("Xem danh sách theo dõi", "Show your watchlist"),
    "/watch": ("Thêm cổ phiếu, vd /watch tesla", "Add a stock, e.g. /watch tesla"),
    "/unwatch": ("Bỏ theo dõi, vd /unwatch tsla", "Remove a stock, e.g. /unwatch tsla"),
    "/language": ("Đổi ngôn ngữ (vi/en)", "Switch language (vi/en)"),
    "/help": ("Danh sách lệnh", "List commands"),
}


def render_help(commands: list[str], *, language: str = "English") -> str:
    """List the registered commands with short descriptions."""
    vi = language.strip().lower() == "vietnamese"
    header = "🤖 Các lệnh có sẵn:" if vi else "🤖 Available commands:"
    lines = [header]
    for cmd in commands:
        desc = _DESCRIPTIONS.get(cmd)
        if desc:
            lines.append(f"{cmd} — {desc[0] if vi else desc[1]}")
        else:
            lines.append(cmd)
    return "\n".join(lines)
