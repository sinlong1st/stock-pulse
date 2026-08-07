"""Render a `BriefingResult` into a Telegram-ready text brief.

Localized by `OUTPUT_LANGUAGE` (English / Vietnamese for now), mirroring the
evaluation digest. A quiet window still produces a short "backdrop holds"
message rather than nothing, because on-demand and anchor briefs always send.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.briefing.models import BriefingResult, BriefingTheme
from app.prices import PriceSnapshot, price_snapshot_line

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


def _time_line(generated_at: datetime, tz_name: str, vi: bool) -> str:
    try:
        local = generated_at.astimezone(ZoneInfo(tz_name))
    except Exception:
        local = generated_at
    stamp = local.strftime("%a %d %b %H:%M")
    abbr = local.tzname() or ""
    return f"🕒 {stamp} {abbr}".strip()


# Enough to show the work without burying the briefing in links.
_MAX_SOURCES = 5


def _source_lines(result: BriefingResult, vi: bool) -> list[str]:
    """Clickable citations for pages the web-search tool actually read.

    Empty unless web search is on. OpenAI requires visible, clickable citations
    when web results are shown to a user, so this is not decoration.
    """
    if not result.sources:
        return []
    out = ["", "🔗 " + ("Nguồn:" if vi else "Sources:")]
    for source in result.sources[:_MAX_SOURCES]:
        label = source.title.strip() or source.url
        out.append(f"  • {label} — {source.url}")
    return out


def _price_block(
    prices: list[PriceSnapshot],
    generated_at: datetime | None,
    tz_name: str,
    vi: bool,
) -> list[str]:
    if not prices:
        return []
    lang = "Vietnamese" if vi else "English"
    out = ["", "💵 " + ("Giá:" if vi else "Prices:")]
    for snap in prices:
        line = price_snapshot_line(snap, now=generated_at, tz_name=tz_name, language=lang)
        out.append(f"  {line}")
    return out


def render_briefing(
    result: BriefingResult,
    *,
    language: str = "English",
    trigger: str = "report",
    subject: str | None = None,
    generated_at: datetime | None = None,
    timezone: str = "UTC",
    prices: list[PriceSnapshot] | None = None,
) -> str:
    vi = _is_vi(language)
    lang = "vi" if vi else "en"
    label = _TRIGGER_LABELS[lang].get(trigger, _TRIGGER_LABELS[lang]["report"])
    title = f"📊 StockPulse — {label}"
    if subject:
        title += f": {subject}"

    header = [title]
    if generated_at is not None:
        header.append(_time_line(generated_at, timezone, vi))

    price_lines = _price_block(prices or [], generated_at, timezone, vi)

    if not result.has_material_update:
        backdrop = (
            "Không có thay đổi lớn — bối cảnh giữ nguyên."
            if vi
            else "No major change — backdrop holds."
        )
        lines = [*header, "", backdrop, *price_lines]
        if result.risk_flags:
            watch = "Theo dõi: " if vi else "Watching: "
            lines.append("")
            lines.append("⚠️ " + watch + "; ".join(result.risk_flags))
        return "\n".join(lines)

    lines = [*header]
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

    lines.extend(price_lines)

    if result.risk_flags:
        lines.append("")
        lines.append("⚠️ " + ("Rủi ro: " if vi else "Risks: ") + "; ".join(result.risk_flags))

    lines.extend(_source_lines(result, vi))

    lines.append("")
    lines.append(
        "ℹ️ Tham khảo, không phải lời khuyên đầu tư."
        if vi
        else "ℹ️ For reference only, not investment advice."
    )
    return "\n".join(lines)
