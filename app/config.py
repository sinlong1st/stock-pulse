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

    # News collection (Phase 1+)
    news_source_name: str = "Yahoo Finance"
    news_rss_url: str = "https://finance.yahoo.com/news/rssindex"

    # Database (Phase 2+)
    database_url: str = "sqlite:///./stockpulse.db"

    # News monitoring (Phase 7+)
    news_check_interval_minutes: int = 10

    # AI classifier (Phase 4+)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    # Telegram notifications (Phase 6+)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

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
