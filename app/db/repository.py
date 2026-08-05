"""Data-access layer for articles.

Keeps SQLAlchemy queries in one place and converts between the ORM row
(`ArticleRow`) and the domain model (`NewsArticle`).
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import AlertRow, ArticleRow, ClassificationRow, PredictionRow
from app.models.article import NewsArticle
from app.models.classification import ClassificationResult
from app.status import (
    PRED_EVALUATED,
    PRED_PENDING,
    PRED_SKIPPED,
    PRED_SOURCE_NEWS,
    PRED_SOURCE_PREDICT,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SENT,
)


def _as_utc(value: datetime | None) -> datetime | None:
    """Coerce a datetime to timezone-aware UTC.

    SQLite does not persist timezone info, so datetimes read back are
    naive; we treat stored values as UTC (that is how we wrote them).
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_model(row: ArticleRow) -> NewsArticle:
    return NewsArticle(
        id=str(row.id),
        source=row.source,
        external_id=row.external_id,
        title=row.title,
        summary=row.summary,
        url=row.url,
        published_at=_as_utc(row.published_at),
        collected_at=_as_utc(row.collected_at),
        content_hash=row.content_hash,
    )


def _to_row(article: NewsArticle) -> ArticleRow:
    return ArticleRow(
        source=article.source,
        external_id=article.external_id,
        title=article.title,
        summary=article.summary,
        url=article.url,
        published_at=article.published_at,
        collected_at=article.collected_at,
        content_hash=article.content_hash,
    )


class ArticleRepository:
    """Read/write articles for a given session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def exists(self, article: NewsArticle) -> bool:
        """True if a matching article is already stored.

        Matches on exact URL, content hash, or (source, external_id) — the
        deduplication signals from the technical plan.
        """
        conditions = [
            ArticleRow.url == article.url,
            ArticleRow.content_hash == article.content_hash,
        ]
        if article.external_id:
            conditions.append(
                and_(
                    ArticleRow.source == article.source,
                    ArticleRow.external_id == article.external_id,
                )
            )
        stmt = select(ArticleRow.id).where(or_(*conditions)).limit(1)
        return self.session.scalar(stmt) is not None

    def add(self, article: NewsArticle) -> ArticleRow:
        """Insert an article (does not commit)."""
        row = _to_row(article)
        self.session.add(row)
        return row

    def get(self, article_id: int) -> NewsArticle | None:
        row = self.session.get(ArticleRow, article_id)
        return _to_model(row) if row else None

    def get_many(self, article_ids: list[int]) -> list[NewsArticle]:
        if not article_ids:
            return []
        stmt = select(ArticleRow).where(ArticleRow.id.in_(article_ids))
        return [_to_model(row) for row in self.session.scalars(stmt)]

    def count(self) -> int:
        return self.session.scalar(select(func.count()).select_from(ArticleRow)) or 0

    def list_recent(self, limit: int = 100) -> list[NewsArticle]:
        """Return stored articles, newest first by publish time.

        Articles without a publish time sort last; ties fall back to
        insertion order (id).
        """
        stmt = (
            select(ArticleRow)
            .order_by(
                ArticleRow.published_at.is_(None),  # False (0) sorts before True (1)
                ArticleRow.published_at.desc(),
                ArticleRow.id.desc(),
            )
            .limit(limit)
        )
        return [_to_model(row) for row in self.session.scalars(stmt)]


def _classification_to_model(row: ClassificationRow) -> ClassificationResult:
    return ClassificationResult(
        is_market_relevant=row.is_market_relevant,
        importance=row.importance,
        category=row.category,
        sentiment=row.sentiment or "NEUTRAL",
        related_tickers=row.related_tickers or [],
        summary=row.summary,
        why_it_matters=row.why_it_matters,
        should_alert=row.should_alert,
        confidence=row.confidence,
    )


class ClassificationRepository:
    """Read/write AI classifications for a given session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def exists_for(self, article_id: int) -> bool:
        stmt = select(ClassificationRow.id).where(
            ClassificationRow.article_id == article_id
        ).limit(1)
        return self.session.scalar(stmt) is not None

    def get_for(self, article_id: int) -> ClassificationResult | None:
        stmt = select(ClassificationRow).where(
            ClassificationRow.article_id == article_id
        ).limit(1)
        row = self.session.scalar(stmt)
        return _classification_to_model(row) if row else None

    def classified_article_ids(self, article_ids: list[int]) -> set[int]:
        """Return which of the given article ids already have a classification."""
        if not article_ids:
            return set()
        stmt = select(ClassificationRow.article_id).where(
            ClassificationRow.article_id.in_(article_ids)
        )
        return set(self.session.scalars(stmt))

    def results_for_articles(self, article_ids: list[int]) -> dict[int, ClassificationResult]:
        """Return stored classifications for the given articles, keyed by article id."""
        if not article_ids:
            return {}
        stmt = select(ClassificationRow).where(ClassificationRow.article_id.in_(article_ids))
        return {row.article_id: _classification_to_model(row) for row in self.session.scalars(stmt)}

    def add(
        self, article_id: int, result: ClassificationResult, *, model: str | None = None
    ) -> ClassificationRow:
        """Insert a classification (does not commit)."""
        row = ClassificationRow(
            article_id=article_id,
            is_market_relevant=result.is_market_relevant,
            importance=result.importance,
            category=result.category,
            sentiment=result.sentiment,
            related_tickers=result.related_tickers,
            summary=result.summary,
            why_it_matters=result.why_it_matters,
            should_alert=result.should_alert,
            confidence=result.confidence,
            model=model,
            created_at=datetime.now(tz=UTC),
        )
        self.session.add(row)
        return row


@dataclass
class AlertView:
    """An alert joined with its article, for display."""

    id: int
    article_title: str
    url: str
    importance: str
    channel: str
    status: str
    created_at: datetime
    sent_at: datetime | None
    error_message: str | None


class AlertRepository:
    """Read/write alert records for a given session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def exists(self, article_id: int, channel: str) -> bool:
        stmt = select(AlertRow.id).where(
            AlertRow.article_id == article_id, AlertRow.channel == channel
        ).limit(1)
        return self.session.scalar(stmt) is not None

    def create(self, article_id: int, importance: str, channel: str) -> AlertRow:
        """Create a PENDING alert record (does not commit)."""
        row = AlertRow(
            article_id=article_id,
            importance=importance,
            channel=channel,
            status=STATUS_PENDING,
            created_at=datetime.now(tz=UTC),
        )
        self.session.add(row)
        return row

    def list_by_status(self, status: str, limit: int = 100) -> list[AlertRow]:
        stmt = (
            select(AlertRow)
            .where(AlertRow.status == status)
            .order_by(AlertRow.created_at.asc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def count_by_status(self, status: str) -> int:
        stmt = select(func.count()).select_from(AlertRow).where(AlertRow.status == status)
        return self.session.scalar(stmt) or 0

    def list_views(self, limit: int = 100) -> list[AlertView]:
        """Return alerts joined with their article, newest first."""
        stmt = (
            select(AlertRow, ArticleRow.title, ArticleRow.url)
            .join(ArticleRow, AlertRow.article_id == ArticleRow.id)
            .order_by(AlertRow.created_at.desc(), AlertRow.id.desc())
            .limit(limit)
        )
        views: list[AlertView] = []
        for alert, title, url in self.session.execute(stmt):
            views.append(
                AlertView(
                    id=alert.id,
                    article_title=title,
                    url=url,
                    importance=alert.importance,
                    channel=alert.channel,
                    status=alert.status,
                    created_at=alert.created_at,
                    sent_at=alert.sent_at,
                    error_message=alert.error_message,
                )
            )
        return views

    def mark_sent(self, alert: AlertRow) -> None:
        alert.status = STATUS_SENT
        alert.sent_at = datetime.now(tz=UTC)
        alert.error_message = None

    def mark_failed(self, alert: AlertRow, error: str) -> None:
        alert.status = STATUS_FAILED
        alert.error_message = error


class PredictionRepository:
    """Read/write self-evaluation predictions for a given session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        ticker: str,
        sentiment: str,
        horizon: str,
        created_at: datetime,
        evaluate_after: datetime,
        baseline_price: float,
        baseline_at: datetime,
        source: str = PRED_SOURCE_NEWS,
        classification_id: int | None = None,
        article_id: int | None = None,
        importance: str | None = None,
        strategy_id: str | None = None,
        confidence: str | None = None,
    ) -> PredictionRow:
        """Record a prediction with its baseline price (does not commit).

        News rows pass classification/article/importance; Predict-tab rows pass
        strategy_id/confidence instead. Everything after `source` is optional so
        each caller only supplies what its kind of prediction actually has.
        """
        row = PredictionRow(
            classification_id=classification_id,
            article_id=article_id,
            source=source,
            ticker=ticker,
            sentiment=sentiment,
            importance=importance,
            strategy_id=strategy_id,
            confidence=confidence,
            horizon=horizon,
            created_at=created_at,
            evaluate_after=evaluate_after,
            baseline_price=baseline_price,
            baseline_at=baseline_at,
            status=PRED_PENDING,
        )
        self.session.add(row)
        return row

    def has_recent_pending(
        self, *, ticker: str, horizon: str, strategy_id: str | None, since: datetime
    ) -> bool:
        """True if an equivalent Predict row is already awaiting evaluation.

        Re-running the same read (a language switch, a second tap) must not
        stack duplicate rows — they would weight one call several times in the
        accuracy stats.
        """
        stmt = (
            select(func.count())
            .select_from(PredictionRow)
            .where(
                PredictionRow.source == PRED_SOURCE_PREDICT,
                PredictionRow.ticker == ticker,
                PredictionRow.horizon == horizon,
                PredictionRow.strategy_id == strategy_id,
                PredictionRow.status == PRED_PENDING,
                PredictionRow.created_at >= since,
            )
        )
        return bool(self.session.scalar(stmt))

    def count(self) -> int:
        return self.session.scalar(select(func.count()).select_from(PredictionRow)) or 0

    def count_by_status(self, status: str) -> int:
        stmt = select(func.count()).select_from(PredictionRow).where(PredictionRow.status == status)
        return self.session.scalar(stmt) or 0

    def list_due(self, now: datetime, limit: int = 200) -> list[PredictionRow]:
        """Pending predictions whose evaluation horizon has passed."""
        stmt = (
            select(PredictionRow)
            .where(
                PredictionRow.status == PRED_PENDING,
                PredictionRow.evaluate_after <= now,
            )
            .order_by(PredictionRow.evaluate_after)
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def mark_evaluated(
        self, prediction: PredictionRow, price_at_horizon: float, return_pct: float, outcome: str
    ) -> None:
        prediction.price_at_horizon = price_at_horizon
        prediction.return_pct = return_pct
        prediction.outcome = outcome
        prediction.status = PRED_EVALUATED
        prediction.evaluated_at = datetime.now(tz=UTC)

    def mark_skipped(self, prediction: PredictionRow) -> None:
        prediction.status = PRED_SKIPPED
        prediction.evaluated_at = datetime.now(tz=UTC)

    def list_evaluated(self, limit: int = 2000, *, source: str | None = None) -> list[PredictionRow]:
        """Evaluated predictions, most recently evaluated first.

        `source` scopes to one kind — the existing accuracy screen asks for
        news only, so Predict-tab reads can't quietly change its numbers.
        """
        stmt = select(PredictionRow).where(PredictionRow.status == PRED_EVALUATED)
        if source is not None:
            stmt = stmt.where(PredictionRow.source == source)
        stmt = stmt.order_by(PredictionRow.evaluated_at.desc(), PredictionRow.id.desc()).limit(limit)
        return list(self.session.scalars(stmt))
