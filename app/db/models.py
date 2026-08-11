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


class PositionExitAnalysisRow(Base):
    """The `position_exit_analyses` table: one row per exit analysis.

    **Capture, not scoring.** Nothing reads these yet. They exist because the
    snapshot is the part that cannot be reconstructed later — the price, the
    levels, the volatility and the verdict *as they were at the moment of the
    call* — while scoring is a pure function over that snapshot plus a future
    price, so it can be written, rewritten or replaced at any time. Waiting for
    the scoring design would have thrown away every analysis made meanwhile, and
    horizons take weeks to mature.

    `evidence_json` holds the whole payload the user actually saw. Spec §25.7 and
    §38 both insist on storing it: without it, a later evaluation is scoring a
    reconstruction rather than the advice that was given, and any change to how
    support levels are computed would silently rewrite history.

    Deliberately **not** in `predictions`: that table scores a *direction* over a
    horizon, and an exit action is not a direction. Forcing `partial-sell` into
    BULLISH/BEARISH would bake a lossy mapping into stored data instead of
    leaving it as a reversible decision in the scorer.
    """

    __tablename__ = "position_exit_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Null for a one-off position typed into the app rather than saved.
    position_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    shares: Mapped[float] = mapped_column(Float)
    average_cost: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    # What was shown, and what each layer said on its own — so a later review can
    # ask whether the rules helped or hurt, not just whether the call was right.
    action: Mapped[str] = mapped_column(String(32), index=True)
    ai_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rules_final: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    # The levels the advice rested on. Kept as columns rather than only inside
    # the JSON because every plausible scorer needs exactly these.
    support: Mapped[float | None] = mapped_column(Float, nullable=True)
    resistance: Mapped[float | None] = mapped_column(Float, nullable=True)
    invalidation: Mapped[float | None] = mapped_column(Float, nullable=True)
    atr14: Mapped[float | None] = mapped_column(Float, nullable=True)
    hold_reward_risk: Mapped[float | None] = mapped_column(Float, nullable=True)
    unrealized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PredictionRow(Base):
    """The `predictions` table: one directional call, scored later against price.

    Two kinds of row live here, told apart by `source`:

    - ``news`` — from the classification pipeline: one per (classification,
      ticker, horizon), carrying `classification_id`/`article_id`/`importance`.
    - ``predict`` — from the Predict tab: one per (ticker, horizon), carrying
      `strategy_id`/`confidence` and no article at all.

    They share a table because the scoring is identical — a direction, a
    baseline price and a deadline — so both feed one evaluation loop.
    """

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Null for `predict` rows: a forward-looking read has no source article.
    classification_id: Mapped[int | None] = mapped_column(
        ForeignKey("classifications.id", ondelete="CASCADE"), index=True, nullable=True
    )
    article_id: Mapped[int | None] = mapped_column(index=True, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="news", index=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    sentiment: Mapped[str] = mapped_column(String(16))
    # `news` rows only — how big a deal the article was.
    importance: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # `predict` rows only — which lens made the call, and how sure it was. The
    # strategy id is what makes per-strategy accuracy possible.
    strategy_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Which model wrote this read ("openai" | "deepseek"). Null on rows recorded
    # before the second-opinion work; those were all OpenAI.
    provider: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    horizon: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evaluate_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    baseline_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING_EVAL", index=True)
    price_at_horizon: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(8), nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
