"""Typed application configuration loaded from environment variables.

Settings are read from the process environment and, if present, a local
``.env`` file, keeping configuration in one typed place.
"""

import logging
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("stockpulse.config")


class Settings(BaseSettings):
    """Application settings.

    Values come from environment variables (case-insensitive) or a `.env`
    file. See `.env.example` for the full list.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_env: str = "development"
    log_level: str = "INFO"
    # Your local timezone — used everywhere a local time matters (quiet
    # hours, the daily digest). One setting for the whole app.
    timezone: str = "Asia/Ho_Chi_Minh"

    # News collection: per-source feeds (separate macro/watchlist fetching).
    # {ticker} and {query} are filled in at runtime.
    yahoo_ticker_feed_url: str = (
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    )
    google_news_rss_url: str = (
        "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    )
    # Separate fetch cadences (minutes) for each source.
    watchlist_fetch_interval_minutes: int = 5
    macro_fetch_interval_minutes: int = 30

    # Database (Phase 2+)
    database_url: str = "sqlite:///./stockpulse.db"

    # News monitoring (Phase 7+)
    # Scheduler is OFF by default — enable it to run the pipeline
    # automatically (which then spends OpenAI credit and sends Telegram
    # messages on its own).
    scheduler_enabled: bool = False
    # Cost caps per scheduled/triggered run.
    max_classifications_per_run: int = 5
    max_alerts_per_run: int = 20

    # AI classifier (Phase 4+)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    # AI prediction (forward-looking, on-demand). See AI_PREDICTION_PLAN.
    prediction_enabled: bool = False
    prediction_horizons: str = "1w,1mo,3mo"  # what the AI reads over
    prediction_model: str = "gpt-4o-mini"
    prediction_range_months: int = 6  # window for the discount/trend signals
    prediction_cache_minutes: int = 180  # reuse a recent read for the same ticker
    # Record each Predict read (tagged with its strategy) so the same evaluation
    # loop scores it later — the data behind per-strategy accuracy. Recording is
    # cheap and best-effort; it reuses the price already fetched for the read.
    prediction_recording_enabled: bool = True
    # Deterministic risk rules that can downgrade the AI's entry advice
    # (committee plan Phase 1). They only ever make it more cautious.
    prediction_rules_enabled: bool = True
    prediction_min_reward_risk: float = 1.5  # below this, entry is downgraded
    prediction_avoid_earnings_days: int = 2  # a report this close overrides the read

    # DeepSeek — an OpenAI-compatible endpoint, used as the second analyst in the
    # committee work. Leave the key blank and everything degrades to OpenAI only.
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"  # the cheap tier; see the plan
    # Language for AI-written summary + why-it-matters (e.g. "English",
    # "Vietnamese"). Alerts inherit this since they use those fields.
    output_language: str = "English"

    # Alerting (Phase 5+). Minimum importance that triggers an alert.
    alert_min_importance: str = "MEDIUM"
    # Alert message options.
    alert_include_link: bool = True  # include the article URL in the message
    alert_link_preview: bool = False  # show Telegram's link preview/thumbnail

    # Quiet hours: hold non-urgent alerts during a daily window (in the
    # user's local timezone); they stay PENDING and go out afterward.
    quiet_hours_enabled: bool = False
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "07:00"
    quiet_hours_min_importance: str = "CRITICAL"  # this level and above always sends

    # Telegram notifications (Phase 6+)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Price data (Alpaca Market Data API). Keys work for paper accounts too.
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_data_url: str = "https://data.alpaca.markets/v2"
    # Yahoo Finance endpoints (keyless): chart = price display, search = resolve
    # a company name to a ticker for /watch.
    yahoo_chart_url: str = "https://query1.finance.yahoo.com"
    yahoo_search_url: str = "https://query1.finance.yahoo.com"
    # quoteSummary carries the earnings calendar + EPS history. Unlike the chart
    # endpoint it is cookie-gated, so app/earnings.py does a crumb handshake.
    yahoo_quote_summary_url: str = "https://query2.finance.yahoo.com"
    price_features_enabled: bool = False
    price_context_in_alerts: bool = False  # add a "MU +3.4% today" line to alerts

    # Earnings calendar + last-quarter EPS, shown in the report and prediction.
    # Best-effort: an outage hides the section, it never fails the request.
    earnings_enabled: bool = True
    earnings_cache_hours: float = 6.0  # earnings move quarterly, not intraday
    earnings_max_tickers: int = 15  # cap the fan-out on a big watchlist

    # Self-evaluation: record AI predictions and later score them vs price.
    evaluation_enabled: bool = False
    evaluation_horizons: str = "1d"  # comma-separated, e.g. "1h,1d"
    evaluation_move_threshold_pct: float = 0.5  # ±band that counts as "flat"
    evaluation_max_move_pct: float = 40.0  # bigger => treat as bad data, skip
    evaluation_check_interval_minutes: int = 15
    # Don't score against a stale price (market closed — weekend/holiday/after
    # hours): defer until a real post-horizon trade prints. Give up after this
    # many days so a delisted ticker can't stay PENDING forever.
    evaluation_stale_grace_days: int = 4
    # Daily self-evaluation digest to Telegram (hour is in TIMEZONE).
    evaluation_digest_enabled: bool = False
    evaluation_digest_hour: int = 8

    # Market Briefing ("the secretary"): a proactive analyst that pulls the
    # latest news on a schedule (and on demand) and reports what matters for
    # the watchlist. Separate pipeline from alerts. See
    # specs/STOCKPULSE_BRIEFING_PLAN.md.
    briefing_enabled: bool = False
    # Runs on US-market / your local (Pacific) time, independent of TIMEZONE.
    briefing_timezone: str = "America/Los_Angeles"
    briefing_schedule_days: str = "mon-fri"  # cron day-of-week for scheduled briefs
    briefing_morning_at: str = "08:30"  # full morning brief
    briefing_intraday_every_hours: int = 2  # 10:30, 12:30, 14:30, 16:30
    briefing_intraday_until: str = "16:30"  # last intraday check-in
    briefing_wrap_at: str = "18:00"  # end-of-day recap
    # Look-back windows (hours) per trigger — see plan §3.
    briefing_morning_window_hours: float = 16.0  # overnight catch-up
    briefing_intraday_window_hours: float = 2.0
    briefing_ondemand_window_hours: float = 2.0
    # Focused single-stock report (/report WDC): wider, since one name may have
    # no news in the last couple hours.
    briefing_focus_window_hours: float = 48.0
    # Analyst model + retrieval. Web search (model pulls news itself) is the
    # Web search runs on the Responses API and needs a search-capable model
    # (gpt-4.1-mini / gpt-4.1 / gpt-5.x). gpt-4o-mini cannot search, so leaving
    # this default with briefing_web_search_enabled=true logs a warning.
    briefing_model: str = "gpt-4o-mini"
    briefing_web_search_enabled: bool = False
    briefing_memory_hours: int = 3  # how far back trend context reaches
    briefing_memory_file: str = "briefing_memory.json"  # rolling theme state
    briefing_max_items: int = 40  # cap news items sent to the model (cost)
    # Show open + current price (with freshness) in briefings. Needs
    # PRICE_FEATURES_ENABLED + Alpaca keys. Capped to limit price lookups.
    briefing_prices_in_report: bool = True
    briefing_price_max_tickers: int = 12  # full /report prices the whole watchlist
    # Price source for the report display: "yahoo" (free, keyless, consolidated
    # + pre/post market — closer to a phone stocks app) or "alpaca" (free IEX
    # feed). Self-evaluation still uses Alpaca regardless.
    briefing_price_source: str = "yahoo"
    # Flag a watchlist stock that moved at least this % today even if it has no
    # news, so the report notes price-driven movers.
    briefing_price_move_threshold_pct: float = 3.0
    # On-demand /report Telegram command (getUpdates listener).
    briefing_command_enabled: bool = False
    briefing_command: str = "/report"

    # Watchlist config file (tickers + company aliases), loaded by
    # app.watchlist. Edit watchlist.json rather than code; see
    # watchlist.example.json for the format.
    watchlist_file: str = "watchlist.json"

    # Keyword config file (macro + sector keywords), loaded by
    # app.keyword_config. See keywords.example.json for the format.
    keywords_file: str = "keywords.json"

    # Runtime user preferences that commands can change live (e.g. the
    # output language via /language). Overrides the env defaults above; in
    # Docker this is redirected into the ./data volume so it survives rebuilds.
    prefs_file: str = "runtime_prefs.json"

    # User-written prediction strategies (app/prediction/store.py). Like
    # prefs_file, redirect this into ./data in Docker so it survives rebuilds.
    strategies_file: str = "strategies.json"

    # Read-only JSON API for the mobile app (GET /api/feed). Off by default and
    # gated by a bearer token; purely additive (does not affect alerts/Telegram).
    mobile_api_enabled: bool = False
    mobile_api_token: str = ""

    # Push notifications (Expo Push API). `push_enabled` gates sending pushes in
    # the alert flow; the register/test endpoints work regardless (for setup).
    # In Docker, push_tokens_file is redirected into the ./data volume.
    push_enabled: bool = False
    push_tokens_file: str = "push_tokens.json"
    expo_access_token: str = ""  # optional; enables Expo's enhanced push security


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


def _resolve_tz(name: str, *, label: str) -> str:
    """Validate a timezone name, falling back to UTC (with a warning)."""
    name = (name or "").strip()
    if name:
        try:
            ZoneInfo(name)
            return name
        except Exception:
            logger.warning("Unknown %s %r; falling back to UTC.", label, name)
    return "UTC"


def resolve_timezone(settings: "Settings | None" = None) -> str:
    """The app's local timezone name, validated.

    Falls back to UTC (with a warning) if the configured name is unknown,
    so a typo never crashes the scheduler at startup.
    """
    settings = settings or get_settings()
    return _resolve_tz(settings.timezone, label="TIMEZONE")


def resolve_briefing_timezone(settings: "Settings | None" = None) -> str:
    """The briefing schedule's timezone (US-market / Pacific), validated.

    Deliberately separate from the app-wide timezone: the briefing follows the
    US market, not the user's quiet-hours locale.
    """
    settings = settings or get_settings()
    return _resolve_tz(settings.briefing_timezone, label="BRIEFING_TIMEZONE")
