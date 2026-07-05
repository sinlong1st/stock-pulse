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
from app.logging_config import configure_logging
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
async def news_page() -> HTMLResponse:
    """A simple read-only page listing the latest collected headlines.

    Debugging aid for humans — open it in a browser instead of reading the
    raw JSON from /collect. Not the future dashboard.
    """
    settings = get_settings()
    collector = RSSCollector(settings.news_source_name, settings.news_rss_url)
    articles = await collector.collect()
    return HTMLResponse(render_news_page(collector.source_name, articles))


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "version": __version__}


@app.get("/collect")
async def collect() -> dict:
    """Manually trigger a one-off news collection (Phase 1 debugging aid).

    Fetches and normalizes recent articles from the configured RSS source
    and returns them. It does not yet store, filter, or alert on anything.
    """
    settings = get_settings()
    collector = RSSCollector(settings.news_source_name, settings.news_rss_url)
    articles = await collector.collect()
    logger.info("Manual /collect fetched %d articles from %s", len(articles), collector.source_name)
    return {
        "source": collector.source_name,
        "count": len(articles),
        "articles": [a.model_dump(mode="json") for a in articles],
    }
