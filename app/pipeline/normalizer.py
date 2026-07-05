"""Convert source-specific feed entries into the common `NewsArticle` model.

Responsibilities (spec Step 2 - Normalize):
- Standardize timestamps to timezone-aware UTC.
- Clean article titles (unescape HTML, collapse whitespace).
- Normalize URLs (drop fragments and common tracking params).
- Generate a stable content hash for duplicate detection.
"""

import hashlib
import re
from calendar import timegm
from datetime import UTC, datetime
from html import unescape
from time import struct_time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.models.article import NewsArticle

_WHITESPACE = re.compile(r"\s+")

# Query params that identify tracking/campaign sources, not the article itself.
_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def clean_title(raw: str | None) -> str:
    """Unescape HTML entities and collapse runs of whitespace."""
    if not raw:
        return ""
    return _WHITESPACE.sub(" ", unescape(raw)).strip()


def normalize_url(raw: str | None) -> str:
    """Return a canonical form of a URL.

    Lowercases scheme/host, drops the fragment, and strips known tracking
    query parameters while preserving meaningful ones (e.g. article ids).
    """
    if not raw:
        return ""
    raw = raw.strip()
    parts = urlsplit(raw)
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _TRACKING_PARAMS]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path,
            urlencode(kept),
            "",  # drop fragment
        )
    )


def struct_time_to_utc(value: struct_time | None) -> datetime | None:
    """Convert feedparser's UTC struct_time into a timezone-aware datetime."""
    if value is None:
        return None
    return datetime.fromtimestamp(timegm(value), tz=UTC)


def compute_content_hash(title: str, summary: str | None) -> str:
    """Fingerprint an article from its cleaned title and summary.

    Deliberately combines more than the title so two different headlines
    linking to the same URL still differ, and duplicate detection does not
    rely on the title alone.
    """
    basis = f"{clean_title(title)}\n{clean_title(summary)}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def normalize_article(
    *,
    source: str,
    raw_title: str | None,
    raw_url: str | None,
    raw_summary: str | None = None,
    published_struct: struct_time | None = None,
    external_id: str | None = None,
    collected_at: datetime | None = None,
) -> NewsArticle | None:
    """Build a `NewsArticle` from raw feed fields.

    Returns ``None`` when the entry lacks the minimum required data
    (a title and a URL), so callers can skip unusable entries.
    """
    title = clean_title(raw_title)
    url = normalize_url(raw_url)
    if not title or not url:
        return None

    summary = clean_title(raw_summary) or None
    return NewsArticle(
        source=source,
        external_id=external_id or None,
        title=title,
        summary=summary,
        url=url,
        published_at=struct_time_to_utc(published_struct),
        collected_at=collected_at or datetime.now(tz=UTC),
        content_hash=compute_content_hash(title, summary),
    )
