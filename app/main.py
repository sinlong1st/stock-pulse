"""StockPulse FastAPI application entrypoint."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app import __version__
from app.alerts import (
    CHANNEL_TELEGRAM,
    NotifierError,
    build_telegram_notifier,
    get_alert_policy,
    send_pending_alerts,
)
from app.alerts.telegram_listener import build_command_listener
from app.api.feed import build_feed
from app.api.report import build_report as build_mobile_report
from app.api.watchlist import build_watchlist
from app.collectors import build_all_collectors, collect_from
from app.commands import build_command_handlers
from app.commands.symbols import resolve_symbol
from app.config import get_settings, resolve_briefing_timezone, resolve_timezone
from app.db import (
    AlertRepository,
    ArticleRepository,
    ClassificationRepository,
    SessionLocal,
)
from app.evaluation import build_evaluation_report, horizons_from_settings
from app.jobs import (
    analyze_relevant_articles,
    intraday_hours,
    parse_hhmm,
    run_daily_digest,
    run_end_of_day_wrap,
    run_evaluation,
    run_intraday_update,
    run_macro_monitor,
    run_morning_brief,
    run_news_monitor,
    run_report,
    run_watchlist_monitor,
)
from app.logging_config import configure_logging
from app.pipeline.classifier import ClassificationError, build_classifier
from app.pipeline.deduplicator import store_new_articles
from app.pipeline.rule_filter import get_rule_filter
from app.prefs import (
    SUPPORTED_LANGUAGES,
    push_delivery_enabled,
    resolve_language,
    set_flag,
    set_language,
    telegram_delivery_enabled,
)
from app.prices import maybe_eval_price_client, maybe_price_client
from app.push.notifier import send_push
from app.push.store import add_token, list_tokens, remove_token
from app.watchlist import add_ticker, remove_ticker
from app.web import render_alerts_page, render_evaluation_page, render_news_page

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
            run_watchlist_monitor,
            "interval",
            minutes=settings.watchlist_fetch_interval_minutes,
            id="watchlist_monitor",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_macro_monitor,
            "interval",
            minutes=settings.macro_fetch_interval_minutes,
            id="macro_monitor",
            max_instances=1,
            coalesce=True,
        )
        if settings.evaluation_enabled:
            scheduler.add_job(
                run_evaluation,
                "interval",
                minutes=settings.evaluation_check_interval_minutes,
                id="evaluation",
                max_instances=1,
                coalesce=True,
            )
            if settings.evaluation_digest_enabled:
                digest_tz = resolve_timezone(settings)
                scheduler.add_job(
                    run_daily_digest,
                    CronTrigger(
                        hour=settings.evaluation_digest_hour,
                        minute=0,
                        timezone=digest_tz,
                    ),
                    id="daily_digest",
                    max_instances=1,
                    coalesce=True,
                )
                logger.info(
                    "Daily digest scheduled at %02d:00 %s.",
                    settings.evaluation_digest_hour,
                    digest_tz,
                )
        if settings.briefing_enabled:
            btz = resolve_briefing_timezone(settings)
            days = settings.briefing_schedule_days
            mh, mm = parse_hhmm(settings.briefing_morning_at)
            scheduler.add_job(
                run_morning_brief,
                CronTrigger(day_of_week=days, hour=mh, minute=mm, timezone=btz),
                id="briefing_morning",
                max_instances=1,
                coalesce=True,
            )
            hours = intraday_hours(settings)
            if hours:
                scheduler.add_job(
                    run_intraday_update,
                    CronTrigger(
                        day_of_week=days,
                        hour=",".join(str(h) for h in hours),
                        minute=mm,
                        timezone=btz,
                    ),
                    id="briefing_intraday",
                    max_instances=1,
                    coalesce=True,
                )
            wh, wm = parse_hhmm(settings.briefing_wrap_at)
            scheduler.add_job(
                run_end_of_day_wrap,
                CronTrigger(day_of_week=days, hour=wh, minute=wm, timezone=btz),
                id="briefing_wrap",
                max_instances=1,
                coalesce=True,
            )
            logger.info(
                "Briefing scheduled (%s): morning %02d:%02d, intraday hours=%s, wrap %02d:%02d %s.",
                days,
                mh,
                mm,
                hours or "none",
                wh,
                wm,
                btz,
            )
        scheduler.start()
        logger.info(
            "Scheduler ENABLED — watchlist every %d min, macro every %d min%s.",
            settings.watchlist_fetch_interval_minutes,
            settings.macro_fetch_interval_minutes,
            (
                f", evaluation every {settings.evaluation_check_interval_minutes} min"
                if settings.evaluation_enabled
                else ""
            ),
        )
    else:
        logger.info("Scheduler disabled (set SCHEDULER_ENABLED=true to automate).")

    # On-demand /report Telegram command — independent of the scheduler, so it
    # works even when automation is off. Locked to the owner chat.
    listener_task: asyncio.Task | None = None
    listener_stop: asyncio.Event | None = None
    if settings.briefing_command_enabled:
        try:
            report_notifier = build_telegram_notifier(settings)
        except NotifierError:
            report_notifier = None
            logger.warning(
                "BRIEFING_COMMAND_ENABLED but Telegram not configured; /report listener off."
            )
        if report_notifier is not None:

            async def _on_report(args: str) -> None:
                vi = resolve_language(settings).strip().lower() == "vietnamese"
                query = args.strip() or None
                if query:
                    ack = (
                        f"⏳ Đang tổng hợp báo cáo về {query}…"
                        if vi
                        else f"⏳ Generating your report on {query}…"
                    )
                else:
                    ack = "⏳ Đang tổng hợp báo cáo…" if vi else "⏳ Generating your report…"
                try:
                    await report_notifier.send(ack)
                except NotifierError:
                    pass
                await run_report(query)

            handlers = build_command_handlers(settings, report_handler=_on_report)
            listener = build_command_listener(settings, handlers=handlers)
            listener_stop = asyncio.Event()
            listener_task = asyncio.create_task(listener.run_forever(listener_stop))
            logger.info(
                "Telegram commands enabled: %s.", ", ".join(sorted(handlers))
            )

    app.state.scheduler = scheduler
    app.state.listener_task = listener_task
    yield

    if listener_stop is not None:
        listener_stop.set()
    if listener_task is not None:
        listener_task.cancel()
        try:
            await listener_task
        except (asyncio.CancelledError, Exception):
            pass
    if scheduler is not None:
        scheduler.shutdown(wait=False)
    logger.info("StockPulse shutting down")


app = FastAPI(title="StockPulse", version=__version__, lifespan=lifespan)

# Permissive CORS so the mobile app (and `npm run web` in a browser) can call
# the read-only JSON API. Endpoints are token-guarded; no cookies are used.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _require_mobile_api(authorization: str | None):
    """Gate the read-only mobile API: enabled + a matching bearer token."""
    settings = get_settings()
    if not settings.mobile_api_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    if not settings.mobile_api_token or authorization != f"Bearer {settings.mobile_api_token}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    return settings


@app.get("/api/feed")
async def api_feed(limit: int = 30, authorization: str | None = Header(default=None)) -> dict:
    """Read-only feed for the mobile app: recent classified articles as JSON.

    Off unless `MOBILE_API_ENABLED=true`, and requires
    `Authorization: Bearer <MOBILE_API_TOKEN>`. Reads only — it does not affect
    the news/alert/Telegram pipeline.
    """
    settings = _require_mobile_api(authorization)
    with SessionLocal() as session:
        alerts = await build_feed(session, settings, limit=min(max(limit, 1), 100))
    return {"alerts": alerts, "generated_at": datetime.now(UTC).isoformat()}


@app.get("/api/watchlist")
async def api_watchlist(authorization: str | None = Header(default=None)) -> dict:
    """Read-only watchlist for the mobile app: your tickers + best-effort prices."""
    settings = _require_mobile_api(authorization)
    with SessionLocal() as session:
        return {"watchlist": await build_watchlist(settings, session=session)}


@app.get("/api/report")
async def api_report(
    q: str | None = None, authorization: str | None = Header(default=None)
) -> dict:
    """Generate a briefing on-demand and return it as JSON (one OpenAI call)."""
    settings = _require_mobile_api(authorization)
    return await build_mobile_report(settings, query=q)


class LanguageBody(BaseModel):
    code: str


class WatchBody(BaseModel):
    query: str


@app.get("/api/settings")
def api_settings(authorization: str | None = Header(default=None)) -> dict:
    """Everything the app's Settings screen shows: language, delivery channels,
    and the (read-only) briefing schedule."""
    settings = _require_mobile_api(authorization)
    current = resolve_language(settings)
    name_to_code = {name: code for code, name in SUPPORTED_LANGUAGES.items()}
    telegram_configured = bool(settings.telegram_bot_token and settings.telegram_chat_id)
    return {
        "language": current,
        "languageCode": name_to_code.get(current),
        "languages": [{"code": c, "name": n} for c, n in SUPPORTED_LANGUAGES.items()],
        "channels": {
            "telegram": {
                "enabled": telegram_delivery_enabled(settings),
                "configured": telegram_configured,
            },
            "push": {"enabled": push_delivery_enabled(settings)},
        },
        "briefing": {
            "enabled": settings.briefing_enabled,
            "timezone": settings.briefing_timezone,
            "morningAt": settings.briefing_morning_at,
            "intradayEveryHours": settings.briefing_intraday_every_hours,
            "intradayUntil": settings.briefing_intraday_until,
            "wrapAt": settings.briefing_wrap_at,
            "editable": False,  # scheduled server-side; app editing not wired yet
        },
    }


class ChannelBody(BaseModel):
    channel: str  # "telegram" | "push"
    enabled: bool


@app.post("/api/settings/channels")
def api_set_channel(body: ChannelBody, authorization: str | None = Header(default=None)) -> dict:
    """Toggle a delivery channel (telegram/push) on or off at runtime."""
    _require_mobile_api(authorization)
    channel = body.channel.strip().lower()
    if channel == "telegram":
        set_flag("telegram_enabled", body.enabled)
    elif channel == "push":
        set_flag("push_enabled", body.enabled)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown channel '{body.channel}'.")
    return {"channel": channel, "enabled": body.enabled}


@app.post("/api/settings/language")
def api_set_language(body: LanguageBody, authorization: str | None = Header(default=None)) -> dict:
    """Switch the output language (en/vi). Same effect as the /language command."""
    _require_mobile_api(authorization)
    code = body.code.strip().lower()
    if code not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language '{body.code}'.")
    name = SUPPORTED_LANGUAGES[code]
    set_language(name)
    return {"language": name, "languageCode": code}


@app.post("/api/watchlist")
async def api_watch_add(body: WatchBody, authorization: str | None = Header(default=None)) -> dict:
    """Add a stock by ticker or company name (resolved via Yahoo)."""
    settings = _require_mobile_api(authorization)
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Empty query.")
    resolved = await resolve_symbol(query, settings=settings)
    if resolved is None:
        return {"added": False, "reason": f"Couldn't find a stock for '{query}'."}
    symbol, name = resolved
    added = add_ticker(symbol, [name] if name and name != symbol else [])
    return {
        "added": added,
        "ticker": symbol,
        "name": name,
        "reason": None if added else f"Already watching {symbol}.",
    }


@app.delete("/api/watchlist/{ticker}")
def api_watch_remove(ticker: str, authorization: str | None = Header(default=None)) -> dict:
    """Remove a ticker from the watchlist."""
    _require_mobile_api(authorization)
    removed = remove_ticker(ticker)
    return {"removed": removed, "ticker": ticker.strip().upper()}


class PushTokenBody(BaseModel):
    token: str
    platform: str | None = None


@app.post("/api/push/register")
def api_push_register(
    body: PushTokenBody, authorization: str | None = Header(default=None)
) -> dict:
    """Register this device's Expo push token."""
    _require_mobile_api(authorization)
    if not body.token.strip():
        raise HTTPException(status_code=400, detail="Empty token.")
    added = add_token(body.token.strip())
    return {"registered": True, "new": added}


@app.post("/api/push/unregister")
def api_push_unregister(
    body: PushTokenBody, authorization: str | None = Header(default=None)
) -> dict:
    """Forget a device's push token (e.g. on sign-out)."""
    _require_mobile_api(authorization)
    removed = remove_token(body.token.strip())
    return {"removed": removed}


@app.post("/api/push/test")
async def api_push_test(authorization: str | None = Header(default=None)) -> dict:
    """Send a test notification to all registered devices (verify the path)."""
    settings = _require_mobile_api(authorization)
    tokens = list_tokens(settings)
    sent = await send_push(
        tokens,
        title="StockPulse",
        body="🔔 Test notification — push is working.",
        data={"type": "test"},
        settings=settings,
    )
    return {"tokens": len(tokens), "sent": sent}


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


@app.get("/evaluation", response_class=HTMLResponse)
def evaluation_page() -> HTMLResponse:
    """Self-evaluation dashboard: accuracy of the AI's directional calls."""
    settings = get_settings()
    with SessionLocal() as session:
        report = build_evaluation_report(session)
    return HTMLResponse(render_evaluation_page(report, language=resolve_language(settings)))


@app.post("/evaluate")
async def evaluate() -> dict:
    """Score predictions whose horizon has passed (manual trigger)."""
    summary = await run_evaluation()
    return {
        "evaluated": summary.evaluated,
        "hits": summary.hits,
        "misses": summary.misses,
        "flats": summary.flats,
        "skipped": summary.skipped,
    }


@app.post("/evaluate/digest")
async def evaluate_digest() -> dict:
    """Send the self-evaluation summary to Telegram now (manual trigger)."""
    sent = await run_daily_digest()
    return {"sent": sent}


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
            language=resolve_language(settings),
            price_client=maybe_price_client(settings),
            push_tokens=list_tokens(settings) if push_delivery_enabled(settings) else None,
            telegram_enabled=telegram_delivery_enabled(settings),
        )
    return {"processed": result.processed, "sent": result.sent, "failed": result.failed}


@app.post("/report")
async def report(q: str | None = None) -> dict:
    """Generate a market briefing right now and send it to Telegram (on-demand).

    The "secretary" trigger: pulls the latest news, has the AI synthesize what
    matters, and delivers it. Always answers (bypasses the materiality gate) —
    a quiet window just gets a short "backdrop holds" note. With `?q=WDC` (or a
    company name, even a typo) it's a focused single-stock report instead of the
    full watchlist. Costs a small amount of OpenAI credit.
    """
    settings = get_settings()
    if not settings.openai_api_key:
        return {"error": "OPENAI_API_KEY is not set.", "hint": "Set OPENAI_API_KEY in .env."}
    run = await run_report(q)
    return {
        "trigger": run.trigger,
        "focus": q or None,
        "collected": run.collected,
        "fresh": run.fresh,
        "unverified": run.unverified,
        "has_material_update": run.has_material_update,
        "urgency": run.urgency,
        "sent": run.sent,
        "skipped_reason": run.skipped_reason,
    }


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
            prediction_price_client=maybe_eval_price_client(settings),
            horizons=horizons_from_settings(settings),
        )

    return {
        "classified": summary.classified,
        "errors": summary.errors,
        "alerts_created": summary.alerts_created,
        "predictions_created": summary.predictions_created,
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
        "alerts_held": summary.alerts_held,
        "predictions_created": summary.predictions_created,
    }


@app.get("/collect")
async def collect() -> dict:
    """Fetch news, store new articles, and skip duplicates.

    Returns a summary of the run. It does not yet filter or alert on
    anything — that arrives in later phases.
    """
    settings = get_settings()
    articles = await collect_from(build_all_collectors(settings))

    with SessionLocal() as session:
        result = store_new_articles(session, articles)

    rule_filter = get_rule_filter()
    relevant = sum(1 for a in articles if rule_filter.is_relevant(a))

    logger.info(
        "Collect (watchlist+macro) -- collected=%d new=%d duplicates=%d relevant=%d stored_total=%d",
        result.collected,
        result.new,
        result.duplicates,
        relevant,
        result.stored_total,
    )
    return {
        "collected": result.collected,
        "new": result.new,
        "duplicates": result.duplicates,
        "relevant": relevant,
        "stored_total": result.stored_total,
    }
