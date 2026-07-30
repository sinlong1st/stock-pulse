"""The /language command: switch the AI output language (en / vi)."""

from pathlib import Path

from app.prefs import SUPPORTED_LANGUAGES, set_language


def _supported_hint(vi: bool) -> str:
    """List of what /language accepts, in the reader's current language."""
    if vi:
        return "Hiện hỗ trợ: en (English), vi (Tiếng Việt)."
    return "Supported: en (English), vi (Vietnamese)."


async def cmd_language(
    args: str, *, language: str = "English", path: str | Path | None = None
) -> str:
    """Set the output language to a supported code, or explain the options."""
    vi = language.strip().lower() == "vietnamese"
    code = args.strip().lower()

    if not code:
        current = (
            f"🌐 Ngôn ngữ hiện tại: {language}."
            if vi
            else f"🌐 Current language: {language}."
        )
        usage = (
            "Dùng: /language vi hoặc /language en."
            if vi
            else "Usage: /language vi or /language en."
        )
        return f"{current}\n{usage}\n{_supported_hint(vi)}"

    if code not in SUPPORTED_LANGUAGES:
        return (
            f"❓ '{args.strip()}' chưa được hỗ trợ. {_supported_hint(vi)}"
            if vi
            else f"❓ '{args.strip()}' isn't supported yet. {_supported_hint(vi)}"
        )

    name = SUPPORTED_LANGUAGES[code]
    set_language(name, path=path)
    # Confirm in the newly chosen language.
    if name.lower() == "vietnamese":
        return f"✅ Đã đổi ngôn ngữ sang {name}. Tin nhắn tiếp theo sẽ dùng ngôn ngữ này."
    return f"✅ Language set to {name}. New messages will use it."
