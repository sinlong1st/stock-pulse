"""Data-access layer for articles.

Keeps SQLAlchemy queries in one place and converts between the ORM row
(`ArticleRow`) and the domain model (`NewsArticle`).
"""

from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import ArticleRow
from app.models.article import NewsArticle


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

    def count(self) -> int:
        return self.session.scalar(select(func.count()).select_from(ArticleRow)) or 0

    def list_recent(self, limit: int = 100) -> list[NewsArticle]:
        """Return stored articles, newest first."""
        stmt = (
            select(ArticleRow)
            .order_by(ArticleRow.collected_at.desc(), ArticleRow.id.desc())
            .limit(limit)
        )
        return [_to_model(row) for row in self.session.scalars(stmt)]
