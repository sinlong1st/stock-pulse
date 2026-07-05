"""The normalized news article model, independent of any source."""

from datetime import datetime

from pydantic import BaseModel, Field


class NewsArticle(BaseModel):
    """A news article normalized into StockPulse's common shape.

    `content_hash` is a stable fingerprint used for duplicate detection in
    later phases; it must not depend on the title alone.
    """

    id: str | None = None
    source: str
    external_id: str | None = None
    title: str
    summary: str | None = None
    url: str
    published_at: datetime | None = None
    collected_at: datetime
    content_hash: str = Field(repr=False)
