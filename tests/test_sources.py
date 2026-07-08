"""Tests for multi-feed collection and the source builders."""

import httpx
import pytest

from app.collectors.multi import MultiRSSCollector
from app.collectors.sources import _macro_query, collect_from

FEED_A = """<?xml version="1.0"?><rss version="2.0"><channel>
  <item><title>NVDA jumps</title><link>https://e.com/nvda</link><guid>a1</guid></item>
  <item><title>Shared story</title><link>https://e.com/shared</link><guid>a2</guid></item>
</channel></rss>"""

FEED_B = """<?xml version="1.0"?><rss version="2.0"><channel>
  <item><title>AMD rallies</title><link>https://e.com/amd</link><guid>b1</guid></item>
  <item><title>Shared story</title><link>https://e.com/shared</link><guid>b2</guid></item>
</channel></rss>"""


def _handler(request: httpx.Request) -> httpx.Response:
    if "feedA" in str(request.url):
        return httpx.Response(200, content=FEED_A.encode())
    if "feedB" in str(request.url):
        return httpx.Response(200, content=FEED_B.encode())
    return httpx.Response(404)


async def test_multi_collector_merges_and_dedupes() -> None:
    collector = MultiRSSCollector(
        "Test",
        ["https://x/feedA", "https://x/feedB"],
        transport=httpx.MockTransport(_handler),
    )
    articles = await collector.collect()
    urls = {a.url for a in articles}
    # 3 unique stories (the shared one is de-duplicated).
    assert urls == {"https://e.com/nvda", "https://e.com/amd", "https://e.com/shared"}


async def test_multi_collector_isolates_a_failing_feed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "good" in str(request.url):
            return httpx.Response(200, content=FEED_A.encode())
        return httpx.Response(500)

    collector = MultiRSSCollector(
        "Test",
        ["https://x/good", "https://x/bad"],
        transport=httpx.MockTransport(handler),
    )
    articles = await collector.collect()
    assert len(articles) == 2  # only the good feed's articles, no crash


async def test_collect_from_isolates_failing_collector() -> None:
    class _Boom:
        source_name = "Boom"

        async def collect(self):
            raise RuntimeError("nope")

    ok = MultiRSSCollector(
        "OK", ["https://x/feedA"], transport=httpx.MockTransport(_handler)
    )
    articles = await collect_from([ok, _Boom()])
    assert len(articles) == 2  # feedA's two articles; Boom skipped


def test_macro_query_quotes_phrases_and_joins_with_or() -> None:
    query = _macro_query(["Federal Reserve", "CPI", "rate cut"])
    assert query == '"Federal Reserve" OR CPI OR "rate cut"'
