"""Deliver pending alerts through the appropriate channel.

Loads PENDING alerts, formats each from its article + classification,
sends it via the matching notifier, and records the outcome (SENT or
FAILED). One failing alert does not stop the batch.
"""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.alerts.constants import STATUS_PENDING
from app.alerts.formatter import format_alert_message
from app.alerts.telegram import Notifier, NotifierError
from app.db.repository import AlertRepository, ArticleRepository, ClassificationRepository

logger = logging.getLogger("stockpulse.alerts.router")


@dataclass
class DeliveryResult:
    processed: int
    sent: int
    failed: int


async def send_pending_alerts(
    session: Session,
    notifiers: dict[str, Notifier],
    *,
    limit: int = 20,
    include_link: bool = True,
) -> DeliveryResult:
    """Send up to `limit` pending alerts and persist their delivery status."""
    alert_repo = AlertRepository(session)
    article_repo = ArticleRepository(session)
    classification_repo = ClassificationRepository(session)

    pending = alert_repo.list_by_status(STATUS_PENDING, limit=limit)
    sent = 0
    failed = 0

    for alert in pending:
        notifier = notifiers.get(alert.channel)
        if notifier is None:
            alert_repo.mark_failed(alert, f"No notifier for channel '{alert.channel}'")
            failed += 1
            continue

        article = article_repo.get(alert.article_id)
        classification = classification_repo.get_for(alert.article_id)
        if article is None or classification is None:
            alert_repo.mark_failed(alert, "Missing article or classification")
            failed += 1
            continue

        message = format_alert_message(article, classification, include_link=include_link)
        try:
            await notifier.send(message)
        except NotifierError as exc:
            logger.warning("Alert %s failed: %s", alert.id, exc)
            alert_repo.mark_failed(alert, str(exc))
            failed += 1
            continue

        alert_repo.mark_sent(alert)
        sent += 1

    session.commit()
    logger.info("Sent %d alerts, %d failed (of %d pending)", sent, failed, len(pending))
    return DeliveryResult(processed=len(pending), sent=sent, failed=failed)
