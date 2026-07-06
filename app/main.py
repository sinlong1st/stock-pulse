"""StockPulse FastAPI application entrypoint.

Phase 0 provides only application startup, logging, and a health check.
News collection, AI classification, and alerting arrive in later phases.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app import __version__
from app.collectors import RSSCollector
from app.config import get_settings
from app.alerts import get_alert_policy
from app.db import (
    AlertRepository,
    ArticleRepository,
    ClassificationRepository,
    SessionLocal,
)
from app.logging_config import configure_logging
from app.pipeline.classifier import ClassificationError, build_classifier
from app.pipeline.deduplicator import store_new_articles
from app.pipeline.rule_filter import get_rule_filter
from app.web import render_news_page

logger = logging.getLogger("stockpulse")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("StockPulse starting (env=%s, version=%s)", settings.app_env, __version__)
    yield
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

    rule_filter = get_rule_filter()
    policy = get_alert_policy()
    settings = get_settings()

    with SessionLocal() as session:
        articles = ArticleRepository(session).list_recent(limit=200)
        classification_repo = ClassificationRepository(session)
        alert_repo = AlertRepository(session)
        already = classification_repo.classified_article_ids(
            [int(a.id) for a in articles if a.id]
        )
        candidates = [
            a
            for a in articles
            if a.id and int(a.id) not in already and rule_filter.is_relevant(a)
        ][:limit]

        results = []
        errors = 0
        alerts_created = 0
        for article in candidates:
            try:
                result = await classifier.classify(article)
            except ClassificationError:
                logger.exception("Classification failed for article %s", article.id)
                errors += 1
                continue
            article_id = int(article.id)
            classification_repo.add(article_id, result, model=settings.openai_model)

            # The app — not the AI — decides whether to alert.
            decision = policy.decide(result)
            if decision.should_alert:
                for channel in decision.channels:
                    if not alert_repo.exists(article_id, channel):
                        alert_repo.create(article_id, decision.importance, channel)
                        alerts_created += 1

            results.append(
                {
                    "article_id": article.id,
                    "title": article.title,
                    "importance": result.importance,
                    "category": result.category,
                    "related_tickers": result.related_tickers,
                    "ai_recommends_alert": result.should_alert,
                    "will_alert": decision.should_alert,
                }
            )
        session.commit()

    logger.info(
        "Classified %d articles (%d errors), created %d alerts",
        len(results),
        errors,
        alerts_created,
    )
    return {
        "classified": len(results),
        "errors": errors,
        "alerts_created": alerts_created,
        "results": results,
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
