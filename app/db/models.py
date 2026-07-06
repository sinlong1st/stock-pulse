"""SQLAlchemy ORM models (database tables)."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ArticleRow(Base):
    """The `articles` table: one row per unique news article.

    Duplicate detection relies on a unique `url` plus indexed
    `content_hash` and `external_id`, so it never depends on title alone.
    """

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(100))
    external_id: Mapped[str | None] = mapped_column(String(500), index=True, nullable=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(String(1000), unique=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)


class ClassificationRow(Base):
    """The `classifications` table: one AI analysis per article."""

    __tablename__ = "classifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    # One classification per article for the MVP (skip reclassifying).
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), unique=True, index=True
    )
    is_market_relevant: Mapped[bool] = mapped_column(Boolean)
    importance: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(16))
    related_tickers: Mapped[list[str]] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text)
    why_it_matters: Mapped[str] = mapped_column(Text)
    should_alert: Mapped[bool] = mapped_column(Boolean)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
