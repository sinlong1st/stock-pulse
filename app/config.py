"""Typed application configuration loaded from environment variables.

Settings are read from the process environment and, if present, a local
``.env`` file. Only Phase 0 values are actively used today; later-phase
values are declared here so configuration stays in one typed place.
"""

from functools import lru_cache

from pydantic import Field, field_validator
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

    # Database (Phase 2+)
    database_url: str = "sqlite:///./stockpulse.db"

    # News monitoring (Phase 7+)
    news_check_interval_minutes: int = 10

    # AI classifier (Phase 4+)
    openai_api_key: str = ""

    # Telegram notifications (Phase 6+)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Watchlist
    watchlist: list[str] = Field(
        default=["QQQ", "QQQM", "VOO", "NVDA", "AMD", "PLTR", "SOFI", "HOOD", "META", "AMZN"]
    )

    @field_validator("watchlist", mode="before")
    @classmethod
    def _split_watchlist(cls, value: object) -> object:
        """Allow WATCHLIST to be a comma-separated string in the environment."""
        if isinstance(value, str):
            return [item.strip().upper() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
