"""Format an alert into a push notification (title + body)."""

from app.models.classification import ClassificationResult

_SENTIMENT_EMOJI = {"BULLISH": "🟢", "BEARISH": "🔴", "NEUTRAL": "⚪"}


def alert_push(classification: ClassificationResult) -> tuple[str, str]:
    """Return (title, body) for a push built from an alert's classification.

    Title packs the at-a-glance signal (sentiment + importance + subject); body
    is the AI summary. e.g. ("🔴 HIGH · NVDA", "Nvidia slips as ...").
    """
    emoji = _SENTIMENT_EMOJI.get(classification.sentiment, "⚪")
    subject = (
        classification.related_tickers[0]
        if classification.related_tickers
        else classification.category
    )
    return f"{emoji} {classification.importance} · {subject}", classification.summary
