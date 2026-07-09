"""Typed application configuration loaded from environment variables.

Settings are read from the process environment and, if present, a local
``.env`` file. Only Phase 0 values are actively used today; later-phase
values are declared here so configuration stays in one typed place.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    quiet_hours_timezone: str = "Asia/Ho_Chi_Minh"
    quiet_hours_min_importance: str = "CRITICAL"  # this level and above always sends

    # Telegram notifications (Phase 6+)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Price data (Alpaca Market Data API). Keys work for paper accounts too.
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_data_url: str = "https://data.alpaca.markets/v2"
    price_features_enabled: bool = False
    price_context_in_alerts: bool = False  # add a "MU +3.4% today" line to alerts

    # Watchlist config file (tickers + company aliases), loaded by
    # app.watchlist. Edit watchlist.json rather than code; see
    # watchlist.example.json for the format.
    watchlist_file: str = "watchlist.json"

    # Keyword config file (macro + sector keywords), loaded by
    # app.keyword_config. See keywords.example.json for the format.
    keywords_file: str = "keywords.json"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
