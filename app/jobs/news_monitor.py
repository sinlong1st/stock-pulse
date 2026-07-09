"""The end-to-end news monitoring job (Phase 7).

Connects every pipeline stage into one run:

    collect -> normalize -> deduplicate -> filter -> classify
            -> decide -> create alerts -> send -> persist

Designed to be safe to run on a schedule: individual article failures do
not abort the batch, and classification/sending are capped per run to
control cost. Classifier and notifier are optional — if their credentials
are missing, those stages are skipped and the run still completes.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.alerts import (
    CHANNEL_TELEGRAM,
    NotifierError,
    build_telegram_notifier,
    get_alert_policy,
    send_pending_alerts,
)
from app.alerts.policy import AlertPolicy
from app.alerts.quiet_hours import is_quiet_now
from app.alerts.telegram import Notifier
from app.collectors import (
    build_all_collectors,
    build_macro_collector,
    build_watchlist_collector,
    collect_from,
)
from app.collectors.base import NewsCollector
from app.config import Settings, get_settings
from app.db import AlertRepository, ArticleRepository, ClassificationRepository, SessionLocal
from app.pipeline.classifier import ClassificationError, Classifier, build_classifier
from app.pipeline.deduplicator import store_new_articles
from app.pipeline.rule_filter import get_rule_filter
from app.prices import maybe_price_client

logger = logging.getLogger("stockpulse.jobs.news_monitor")

_UNSET = object()

# Serializes the classify + alert stage so two source jobs (watchlist and
# macro) running on different cadences never classify the same article twice.
_analyze_lock = asyncio.Lock()


@dataclass
class AnalyzeSummary:
    classified: int = 0
    errors: int = 0
    alerts_created: int = 0


@dataclass
class MonitorSummary:
    collected: int = 0
    new: int = 0
    duplicates: int = 0
    relevant: int = 0
    classified: int = 0
    errors: int = 0
    alerts_created: int = 0
    alerts_sent: int = 0
    alerts_failed: int = 0
    alerts_held: int = 0


async def analyze_relevant_articles(
    session: Session,
    *,
    classifier: Classifier,
    policy: AlertPolicy,
    model: str | None,
    limit: int,
    article_ids: list[int] | None = None,
) -> AnalyzeSummary:
    """Classify relevant, not-yet-classified articles and create alerts.

    With `article_ids`, only those articles are considered (scheduled jobs
    pass the batch they just fetched, so each source alerts on its own
    cadence). Without it, the newest stored articles are used (manual
    /classify). One bad article is logged and skipped without aborting.
    """
    rule_filter = get_rule_filter()
    article_repo = ArticleRepository(session)
    classification_repo = ClassificationRepository(session)
    alert_repo = AlertRepository(session)

    if article_ids is None:
        articles = article_repo.list_recent(limit=200)
    else:
        articles = article_repo.get_many(article_ids)
    already = classification_repo.classified_article_ids([int(a.id) for a in articles if a.id])
    candidates = [
        a for a in articles if a.id and int(a.id) not in already and rule_filter.is_relevant(a)
    ]
    # Newest first, then cap (so a big batch classifies the freshest items).
    candidates.sort(
        key=lambda a: a.published_at or datetime.min.replace(tzinfo=UTC), reverse=True
    )
    candidates = candidates[:limit]

    summary = AnalyzeSummary()
    for article in candidates:
        try:
            result = await classifier.classify(article)
        except ClassificationError:
            logger.exception("Classification failed for article %s", article.id)
            summary.errors += 1
            continue

        article_id = int(article.id)
        classification_repo.add(article_id, result, model=model)
        summary.classified += 1

        decision = policy.decide(result)
        if decision.should_alert:
            for channel in decision.channels:
                if not alert_repo.exists(article_id, channel):
                    alert_repo.create(article_id, decision.importance, channel)
                    summary.alerts_created += 1

    session.commit()
    return summary


async def run_news_monitor(
    *,
    session_factory=SessionLocal,
    settings: Settings | None = None,
    collectors: list[NewsCollector] | None = None,
    classifier: object = _UNSET,
    notifier: object = _UNSET,
    label: str = "all",
) -> MonitorSummary:
    """Run the full pipeline once for the given collectors and return a summary.

    `collectors` defaults to both sources (watchlist + macro). `classifier`/
    `notifier` default to being built from settings (or None if credentials
    are missing); pass explicit values (including None) to override, which is
    what the tests do.
    """
    settings = settings or get_settings()
    if collectors is None:
        collectors = build_all_collectors(settings)
    policy = get_alert_policy()
    rule_filter = get_rule_filter()

    if classifier is _UNSET:
        try:
            classifier = build_classifier(settings)
        except ClassificationError:
            logger.warning("OPENAI_API_KEY not set — skipping classification this run.")
            classifier = None
    if notifier is _UNSET:
        try:
            notifier = build_telegram_notifier(settings)
        except NotifierError:
            logger.warning("Telegram credentials not set — leaving alerts pending.")
            notifier = None

    summary = MonitorSummary()

    # 1. Collect + 2. Store/dedupe.
    articles = await collect_from(collectors)
    with session_factory() as session:
        store = store_new_articles(session, articles)
    summary.collected = store.collected
    summary.new = store.new
    summary.duplicates = store.duplicates
    summary.relevant = sum(1 for a in articles if rule_filter.is_relevant(a))

    # 3 + 4. Classify/decide/alert, serialized so overlapping source jobs
    # never process the same article twice.
    async with _analyze_lock:
        if classifier is not None:
            with session_factory() as session:
                analyzed = await analyze_relevant_articles(
                    session,
                    classifier=classifier,
                    policy=policy,
                    model=settings.openai_model,
                    limit=settings.max_classifications_per_run,
                    article_ids=store.new_ids,  # only this source's fresh batch
                )
            summary.classified = analyzed.classified
            summary.errors = analyzed.errors
            summary.alerts_created = analyzed.alerts_created

        if notifier is not None:
            with session_factory() as session:
                delivery = await send_pending_alerts(
                    session,
                    {CHANNEL_TELEGRAM: notifier},
                    limit=settings.max_alerts_per_run,
                    include_link=settings.alert_include_link,
                    language=settings.output_language,
                    quiet_now=is_quiet_now(settings),
                    quiet_min_importance=settings.quiet_hours_min_importance,
                    price_client=maybe_price_client(settings),
                )
            summary.alerts_sent = delivery.sent
            summary.alerts_failed = delivery.failed
            summary.alerts_held = delivery.held

    logger.info(
        "News monitor [%s] -- collected=%d new=%d duplicates=%d relevant=%d "
        "classified=%d errors=%d alerts_created=%d sent=%d failed=%d held=%d",
        label,
        summary.collected,
        summary.new,
        summary.duplicates,
        summary.relevant,
        summary.classified,
        summary.errors,
        summary.alerts_created,
        summary.alerts_sent,
        summary.alerts_failed,
        summary.alerts_held,
    )
    return summary


async def run_watchlist_monitor() -> MonitorSummary:
    """Scheduled job: fetch watchlist (per-ticker) news, then analyze + alert."""
    return await run_news_monitor(
        collectors=[build_watchlist_collector()], label="watchlist"
    )


async def run_macro_monitor() -> MonitorSummary:
    """Scheduled job: fetch macro news, then analyze + alert."""
    return await run_news_monitor(collectors=[build_macro_collector()], label="macro")
