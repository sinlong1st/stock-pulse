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
from app.db import ArticleRepository, SessionLocal
from app.logging_config import configure_logging
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
    rule_filter = get_rule_filter()
    evaluations = [rule_filter.evaluate(a) for a in articles]
    return HTMLResponse(render_news_page(articles, stored_total=total, evaluations=evaluations))


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "version": __version__}


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
