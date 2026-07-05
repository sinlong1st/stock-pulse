"""Unit tests for the RSS collector.

Parsing is tested against a static feed; the network fetch is exercised
with an httpx MockTransport so no real HTTP request is made.
"""

import httpx

from app.collectors.rss import RSSCollector

SAMPLE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Sample Finance Feed</title>
    <item>
      <title>Fed signals rate cuts may be delayed</title>
      <link>https://example.com/fed?utm_source=rss</link>
      <description>Powell comments push yields higher.</description>
      <guid>guid-1</guid>
      <pubDate>Sat, 05 Jul 2026 13:00:00 GMT</pubDate>
    </item>
    <item>
      <title>NVDA hits new high</title>
      <link>https://example.com/nvda</link>
      <description>Nvidia rallies on AI demand.</description>
      <guid>guid-2</guid>
      <pubDate>Sat, 05 Jul 2026 14:00:00 GMT</pubDate>
    </item>
    <item>
      <link>https://example.com/no-title</link>
      <description>Entry without a title should be skipped.</description>
    </item>
  </channel>
</rss>
"""


def test_parse_returns_normalized_articles_and_skips_untitled() -> None:
    collector = RSSCollector("Test Source", "https://example.com/feed")
    articles = collector.parse(SAMPLE_FEED)

    assert len(articles) == 2  # untitled entry skipped
    first = articles[0]
    assert first.source == "Test Source"
    assert first.title == "Fed signals rate cuts may be delayed"
    assert first.url == "https://example.com/fed"  # tracking param stripped
    assert first.external_id == "guid-1"
    assert first.published_at is not None
    assert first.content_hash


async def test_collect_fetches_over_http_with_mock_transport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.com/feed"
        return httpx.Response(200, content=SAMPLE_FEED.encode("utf-8"))

    collector = RSSCollector(
        "Test Source",
        "https://example.com/feed",
        transport=httpx.MockTransport(handler),
    )
    articles = await collector.collect()
    assert len(articles) == 2
    assert articles[1].title == "NVDA hits new high"
