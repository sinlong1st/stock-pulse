"""Deduplication stage (pipeline Step 3).

Filters a freshly collected batch down to articles that are neither
already stored nor repeated within the same batch.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.db.repository import ArticleRepository
from app.models.article import NewsArticle


def partition_new_articles(
    repository: ArticleRepository, articles: list[NewsArticle]
) -> list[NewsArticle]:
    """Return only articles not seen before.

    Skips items already in the database and collapses duplicates that
    appear more than once within this same batch.
    """
    new: list[NewsArticle] = []
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()

    for article in articles:
        if article.url in seen_urls or article.content_hash in seen_hashes:
            continue
        if repository.exists(article):
            continue
        seen_urls.add(article.url)
        seen_hashes.add(article.content_hash)
        new.append(article)

    return new


@dataclass
class StoreResult:
    """Outcome of storing a collected batch."""

    collected: int
    new: int
    duplicates: int
    stored_total: int
    new_ids: list[int] = field(default_factory=list)


def store_new_articles(session: Session, articles: list[NewsArticle]) -> StoreResult:
    """Deduplicate a batch against the DB, persist the new ones, and commit."""
    repository = ArticleRepository(session)
    new_articles = partition_new_articles(repository, articles)
    rows = [repository.add(article) for article in new_articles]
    session.commit()
    return StoreResult(
        collected=len(articles),
        new=len(new_articles),
        duplicates=len(articles) - len(new_articles),
        stored_total=repository.count(),
        new_ids=[row.id for row in rows],
    )
