"""Format an alert into a human-readable notification message."""

from app.models.article import NewsArticle
from app.models.classification import ClassificationResult

_IMPORTANCE_EMOJI = {"MEDIUM": "⚠️", "HIGH": "🚨", "CRITICAL": "🔴"}
_SENTIMENT_TAG = {
    "BULLISH": "🟢 Bullish",
    "BEARISH": "🟠 Bearish",
    "NEUTRAL": "⚪ Neutral",
}


def format_alert_message(
    article: NewsArticle,
    classification: ClassificationResult,
    *,
    include_link: bool = True,
) -> str:
    """Build the plain-text alert body (used for Telegram and logs).

    Leads with the AI summary and reasoning; the article title comes after
    the source (the title is also in the link). The URL is optional.
    """
    emoji = _IMPORTANCE_EMOJI.get(classification.importance, "📰")
    sentiment = _SENTIMENT_TAG.get(classification.sentiment, "⚪ Neutral")
    tickers = ", ".join(classification.related_tickers) if classification.related_tickers else "—"
    lines = [
        f"{emoji} {classification.importance} · {classification.category} · {sentiment}",
        "",
        classification.summary,
        "",
        f"Why it matters: {classification.why_it_matters}",
        f"Likely affected: {tickers}",
        "",
        f"Source: {article.source}",
        article.title,
    ]
    if include_link and article.url:
        lines.append(article.url)
    return "\n".join(lines)
