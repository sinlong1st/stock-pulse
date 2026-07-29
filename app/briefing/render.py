"""Render a `BriefingResult` into a Telegram-ready text brief.

Localized by `OUTPUT_LANGUAGE` (English / Vietnamese for now), mirroring the
evaluation digest. A quiet window still produces a short "backdrop holds"
message rather than nothing, because on-demand and anchor briefs always send.
"""

from app.briefing.models import BriefingResult, BriefingTheme

_DIRECTION_EMOJI = {"bullish": "🟢", "bearish": "🟠", "mixed": "⚪"}

_TRIGGER_LABELS = {
    "en": {
        "morning": "Morning brief",
        "intraday": "Update",
        "wrap": "End-of-day wrap",
        "report": "On-demand report",
    },
    "vi": {
        "morning": "Bản tin sáng",
        "intraday": "Cập nhật",
        "wrap": "Tổng kết cuối ngày",
        "report": "Báo cáo nhanh",
    },
}

_TREND_LABELS = {
    "en": {
        "new": "new",
        "strengthening": "strengthening",
        "fading": "fading",
        "reversing": "reversing",
    },
    "vi": {
        "new": "mới",
        "strengthening": "đang mạnh lên",
        "fading": "đang yếu đi",
        "reversing": "đảo chiều",
    },
}


def _is_vi(language: str) -> bool:
    return (language or "").strip().lower() == "vietnamese"


def _theme_line(theme: BriefingTheme, vi: bool) -> str:
    emoji = _DIRECTION_EMOJI.get(theme.direction, "⚪")
    trend = _TREND_LABELS["vi" if vi else "en"].get(theme.trend, theme.trend)
    tickers = f" ({', '.join(theme.tickers)})" if theme.tickers else ""
    bg = ""
    if theme.freshness == "background":
        bg = " · nền" if vi else " · background"
    head = f"{emoji} {theme.theme}{tickers} · {trend}{bg}"
    return f"{head}\n   {theme.insight}"


def render_briefing(
    result: BriefingResult,
    *,
    language: str = "English",
    trigger: str = "report",
    subject: str | None = None,
) -> str:
    vi = _is_vi(language)
    lang = "vi" if vi else "en"
    label = _TRIGGER_LABELS[lang].get(trigger, _TRIGGER_LABELS[lang]["report"])
    title = f"📊 StockPulse — {label}"
    if subject:
        title += f": {subject}"

    if not result.has_material_update:
        backdrop = (
            "Không có thay đổi lớn — bối cảnh giữ nguyên."
            if vi
            else "No major change — backdrop holds."
        )
        lines = [title, "", backdrop]
        if result.risk_flags:
            lines.append("")
            lines.append("⚠️ " + ("Theo dõi: " if vi else "Watching: ") + "; ".join(result.risk_flags))
        return "\n".join(lines)

    lines = [title]
    if result.urgency == "urgent":
        prefix = "🔴 Khẩn: " if vi else "🔴 Urgent: "
        lines.append(prefix + (result.headline or ""))
    elif result.headline:
        lines.append(result.headline)
    lines.append("")

    for theme in result.themes:
        lines.append(_theme_line(theme, vi))

    if result.watchlist_notes:
        lines.append("")
        lines.append("📌 Watchlist:")
        for note in result.watchlist_notes:
            emoji = _DIRECTION_EMOJI.get(note.direction, "⚪")
            lines.append(f"{emoji} {note.ticker}: {note.note}")

    if result.risk_flags:
        lines.append("")
        lines.append("⚠️ " + ("Rủi ro: " if vi else "Risks: ") + "; ".join(result.risk_flags))

    lines.append("")
    lines.append(
        "ℹ️ Tham khảo, không phải lời khuyên đầu tư."
        if vi
        else "ℹ️ For reference only, not investment advice."
    )
    return "\n".join(lines)
