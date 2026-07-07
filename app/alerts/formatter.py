"""Format an alert into a human-readable notification message."""

from app.models.article import NewsArticle
from app.models.classification import ClassificationResult

_IMPORTANCE_EMOJI = {"MEDIUM": "⚠️", "HIGH": "🚨", "CRITICAL": "🔴"}


def format_alert_message(article: NewsArticle, classification: ClassificationResult) -> str:
    """Build the plain-text alert body (used for Telegram and logs)."""
    emoji = _IMPORTANCE_EMOJI.get(classification.importance, "📰")
    tickers = ", ".join(classification.related_tickers) if classification.related_tickers else "—"
    lines = [
        f"{emoji} {classification.importance} {classification.category} NEWS",
        "",
        article.title,
        "",
        f"Why it matters: {classification.why_it_matters}",
        f"Likely affected: {tickers}",
        f"Source: {article.source}",
    ]
    if article.url:
        lines.append(article.url)
    return "\n".join(lines)
