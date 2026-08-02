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
from app.alerts.policy import IMPORTANCE_ORDER
from app.alerts.telegram import Notifier, NotifierError
from app.db.repository import AlertRepository, ArticleRepository, ClassificationRepository
from app.prices import PriceClient, price_context_line
from app.push.messages import alert_push
from app.push.notifier import send_push

logger = logging.getLogger("stockpulse.alerts.router")


@dataclass
class DeliveryResult:
    processed: int
    sent: int
    failed: int
    held: int = 0  # deferred by quiet hours (still PENDING)


async def send_pending_alerts(
    session: Session,
    notifiers: dict[str, Notifier],
    *,
    limit: int = 20,
    include_link: bool = True,
    language: str = "English",
    quiet_now: bool = False,
    quiet_min_importance: str = "CRITICAL",
    price_client: PriceClient | None = None,
    push_tokens: list[str] | None = None,
    telegram_enabled: bool = True,
) -> DeliveryResult:
    """Send up to `limit` pending alerts and persist their delivery status.

    During quiet hours (`quiet_now`), alerts below `quiet_min_importance`
    are held: left PENDING and counted, not sent.

    When `push_tokens` is given, each alert that goes out also fires a push
    notification to those devices (best-effort; a push failure never affects the
    alert's SENT status). Push mirrors what's sent, so it inherits the same
    quiet-hours + importance gating.
    """
    alert_repo = AlertRepository(session)
    article_repo = ArticleRepository(session)
    classification_repo = ClassificationRepository(session)

    pending = alert_repo.list_by_status(STATUS_PENDING, limit=limit)
    quiet_floor = IMPORTANCE_ORDER.get(quiet_min_importance.upper(), 3)
    sent = 0
    failed = 0
    held = 0

    for alert in pending:
        if quiet_now and IMPORTANCE_ORDER.get(alert.importance, 0) < quiet_floor:
            held += 1  # deferred; stays PENDING for a later send
            continue

        article = article_repo.get(alert.article_id)
        classification = classification_repo.get_for(alert.article_id)
        if article is None or classification is None:
            alert_repo.mark_failed(alert, "Missing article or classification")
            failed += 1
            continue

        delivered = False
        telegram_error: str | None = None

        # Channel 1 — Telegram (the alert's channel). Optional per settings.
        notifier = notifiers.get(alert.channel) if telegram_enabled else None
        if notifier is not None:
            price_line = None
            if price_client is not None and classification.related_tickers:
                try:
                    move = await price_client.change_today(classification.related_tickers[0])
                    if move is not None:
                        price_line = price_context_line(move, language)
                except Exception:  # price is best-effort; never block an alert
                    logger.debug("Price lookup failed for alert %s", alert.id, exc_info=True)
            message = format_alert_message(
                article,
                classification,
                include_link=include_link,
                language=language,
                price_line=price_line,
            )
            try:
                await notifier.send(message)
                delivered = True
            except NotifierError as exc:
                telegram_error = str(exc)
                logger.warning("Alert %s telegram send failed: %s", alert.id, exc)

        # Channel 2 — app push (independent, best-effort). Dispatch counts as
        # delivery so an alert isn't stuck PENDING when Telegram is off.
        if push_tokens:
            title, body = alert_push(classification)
            await send_push(
                push_tokens,
                title=title,
                body=body,
                data={"type": "alert", "alertId": alert.id, "articleId": alert.article_id},
            )
            delivered = True

        if delivered:
            alert_repo.mark_sent(alert)
            sent += 1
        else:
            alert_repo.mark_failed(alert, telegram_error or "No delivery channel enabled")
            failed += 1

    session.commit()
    logger.info(
        "Sent %d alerts, %d failed, %d held (of %d pending)",
        sent,
        failed,
        held,
        len(pending),
    )
    return DeliveryResult(processed=len(pending), sent=sent, failed=failed, held=held)
