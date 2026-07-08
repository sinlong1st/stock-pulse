"""SQLAlchemy ORM models (database tables)."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
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
    sentiment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    related_tickers: Mapped[list[str]] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text)
    why_it_matters: Mapped[str] = mapped_column(Text)
    should_alert: Mapped[bool] = mapped_column(Boolean)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AlertRow(Base):
    """The `alerts` table: one delivery attempt per (article, channel)."""

    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("article_id", "channel", name="uq_alert_article_channel"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), index=True
    )
    importance: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
