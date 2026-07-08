"""Format an alert into a human-readable notification message.

Fixed labels are localized by language (from OUTPUT_LANGUAGE). Add a new
language by adding an entry to ``_LABELS``; unknown languages fall back to
English.
"""

from app.models.article import NewsArticle
from app.models.classification import ClassificationResult

_IMPORTANCE_EMOJI = {"MEDIUM": "⚠️", "HIGH": "🚨", "CRITICAL": "🔴"}
_SENTIMENT_EMOJI = {"BULLISH": "🟢", "BEARISH": "🟠", "NEUTRAL": "⚪"}

# Localized labels, keyed by lowercased language name.
_LABELS: dict[str, dict[str, str]] = {
    "english": {
        "why": "Why it matters",
        "affected": "Likely affected",
        "source": "Source",
        "BULLISH": "Bullish",
        "BEARISH": "Bearish",
        "NEUTRAL": "Neutral",
    },
    "vietnamese": {
        "why": "Vì sao quan trọng",
        "affected": "Ảnh hưởng",
        "source": "Nguồn",
        "BULLISH": "Tăng giá",
        "BEARISH": "Giảm giá",
        "NEUTRAL": "Trung tính",
    },
}


def _labels(language: str) -> dict[str, str]:
    return _LABELS.get(language.strip().lower(), _LABELS["english"])


def format_alert_message(
    article: NewsArticle,
    classification: ClassificationResult,
    *,
    include_link: bool = True,
    language: str = "English",
) -> str:
    """Build the plain-text alert body (used for Telegram and logs).

    Leads with the AI summary and reasoning; the article title comes after
    the source (the title is also in the link). Labels follow `language`;
    the URL is optional.
    """
    labels = _labels(language)
    emoji = _IMPORTANCE_EMOJI.get(classification.importance, "📰")
    sentiment_emoji = _SENTIMENT_EMOJI.get(classification.sentiment, "⚪")
    sentiment_word = labels.get(classification.sentiment, "Neutral")
    tickers = ", ".join(classification.related_tickers) if classification.related_tickers else "—"
    lines = [
        f"{emoji} {classification.importance} · {classification.category} "
        f"· {sentiment_emoji} {sentiment_word}",
        "",
        classification.summary,
        "",
        f"{labels['why']}: {classification.why_it_matters}",
        f"{labels['affected']}: {tickers}",
        "",
        f"{labels['source']}: {article.source}",
        article.title,
    ]
    if include_link and article.url:
        lines.append(article.url)
    return "\n".join(lines)
