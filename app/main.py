"""StockPulse FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app import __version__
from app.alerts import (
    CHANNEL_TELEGRAM,
    NotifierError,
    build_telegram_notifier,
    get_alert_policy,
    send_pending_alerts,
)
from app.collectors import RSSCollector
from app.config import get_settings
from app.db import (
    AlertRepository,
    ArticleRepository,
    ClassificationRepository,
    SessionLocal,
)
from app.jobs import analyze_relevant_articles, run_news_monitor
from app.logging_config import configure_logging
from app.pipeline.classifier import ClassificationError, build_classifier
from app.pipeline.deduplicator import store_new_articles
from app.pipeline.rule_filter import get_rule_filter
from app.web import render_alerts_page, render_news_page

logger = logging.getLogger("stockpulse")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("StockPulse starting (env=%s, version=%s)", settings.app_env, __version__)

    scheduler: AsyncIOScheduler | None = None
    if settings.scheduler_enabled:
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            run_news_monitor,
            "interval",
            minutes=settings.news_check_interval_minutes,
            id="news_monitor",
            max_instances=1,  # never overlap runs
            coalesce=True,  # collapse missed runs into one
        )
        scheduler.start()
        logger.info(
            "Scheduler ENABLED — running news monitor every %d min.",
            settings.news_check_interval_minutes,
        )
    else:
        logger.info("Scheduler disabled (set SCHEDULER_ENABLED=true to automate).")

    app.state.scheduler = scheduler
    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)
    logger.info("StockPulse shutting down")


app = FastAPI(title="StockPulse", version=__version__, lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def news_page() -> HTMLResponse:
    """A simple read-only page listing articles already stored in the DB.

    Use the "Fetch latest news" button (which calls /collect) to pull and
    store new articles, then this page shows the accumulated, de-duplicated
    result. Not the future dashboard.
    """
    with SessionLocal() as session:
        repository = ArticleRepository(session)
        articles = repository.list_recent(limit=100)
        total = repository.count()
        article_ids = [int(a.id) for a in articles if a.id]
        classifications = ClassificationRepository(session).results_for_articles(article_ids)
    rule_filter = get_rule_filter()
    evaluations = [rule_filter.evaluate(a) for a in articles]
    # Key classifications by the article's string id to match NewsArticle.id.
    classification_map = {str(aid): result for aid, result in classifications.items()}
    return HTMLResponse(
        render_news_page(
            articles,
            stored_total=total,
            evaluations=evaluations,
            classifications=classification_map,
        )
    )


@app.get("/alerts", response_class=HTMLResponse)
def alerts_page() -> HTMLResponse:
    """A page listing alert records and their delivery status."""
    with SessionLocal() as session:
        alerts = AlertRepository(session).list_views(limit=200)
    return HTMLResponse(render_alerts_page(alerts))


@app.post("/alerts/send")
async def send_alerts(limit: int = 20) -> dict:
    """Send PENDING alerts to Telegram and record their status (manual)."""
    try:
        notifier = build_telegram_notifier()
    except NotifierError as exc:
        return {
            "error": str(exc),
            "hint": "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env.",
        }

    settings = get_settings()
    with SessionLocal() as session:
        result = await send_pending_alerts(
            session,
            {CHANNEL_TELEGRAM: notifier},
            limit=limit,
            include_link=settings.alert_include_link,
        )
    return {"processed": result.processed, "sent": result.sent, "failed": result.failed}


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "version": __version__}


@app.post("/classify")
async def classify(limit: int = 5) -> dict:
    """Classify stored, relevant, not-yet-classified articles with the AI.

    Manual/opt-in so it never spends API budget automatically. Picks up to
    `limit` articles, calls the AI, validates and stores each result, and
    skips articles that already have a classification (cost control).
    """
    try:
        classifier = build_classifier()
    except ClassificationError as exc:
        return {"error": str(exc), "hint": "Set OPENAI_API_KEY in .env."}

    policy = get_alert_policy()
    settings = get_settings()

    with SessionLocal() as session:
        summary = await analyze_relevant_articles(
            session,
            classifier=classifier,
            policy=policy,
            model=settings.openai_model,
            limit=limit,
        )

    return {
        "classified": summary.classified,
        "errors": summary.errors,
        "alerts_created": summary.alerts_created,
    }


@app.post("/run")
async def run_pipeline() -> dict:
    """Run the full pipeline once, right now (collect → … → send).

    Manual trigger — the same job the scheduler runs. Costs OpenAI credit
    (classifying new matches) and sends Telegram messages if configured.
    """
    summary = await run_news_monitor()
    return {
        "collected": summary.collected,
        "new": summary.new,
        "duplicates": summary.duplicates,
        "relevant": summary.relevant,
        "classified": summary.classified,
        "errors": summary.errors,
        "alerts_created": summary.alerts_created,
        "alerts_sent": summary.alerts_sent,
        "alerts_failed": summary.alerts_failed,
    }


@app.get("/collect")
async def collect() -> dict:
    """Fetch news, store new articles, and skip duplicates.

    Returns a summary of the run. It does not yet filter or alert on
    anything — that arrives in later phases.
    """
    settings = get_settings()
    collector = RSSCollector(settings.news_source_name, settings.news_rss_url)
    articles = await collector.collect()

    with SessionLocal() as session:
        result = store_new_articles(session, articles)

    rule_filter = get_rule_filter()
    relevant = sum(1 for a in articles if rule_filter.is_relevant(a))

    logger.info(
        "Collect from %s -- collected=%d new=%d duplicates=%d relevant=%d stored_total=%d",
        collector.source_name,
        result.collected,
        result.new,
        result.duplicates,
        relevant,
        result.stored_total,
    )
    return {
        "source": collector.source_name,
        "collected": result.collected,
        "new": result.new,
        "duplicates": result.duplicates,
        "relevant": relevant,
        "stored_total": result.stored_total,
    }
