"""Tests for report timestamp + open/current price in briefings."""

from datetime import UTC, datetime, timedelta

from app.briefing.models import BriefingResult, BriefingTheme, WatchlistNote
from app.briefing.render import render_briefing
from app.briefing.retrieval import RetrievalResult, assess_freshness
from app.jobs.briefing import run_report
from app.config import Settings
from app.models.article import NewsArticle
from app.prices import PriceClient, PriceSnapshot

NOW = datetime(2026, 7, 28, 20, 0, tzinfo=UTC)


def _snap(ticker: str) -> PriceSnapshot:
    return PriceSnapshot(
        ticker=ticker, price=65.2, price_time=NOW - timedelta(minutes=3), open=64.1, prev_close=63.5
    )


# --- render ----------------------------------------------------------------


def test_render_includes_report_timestamp() -> None:
    result = BriefingResult(has_material_update=False)
    text = render_briefing(
        result, generated_at=NOW, timezone="America/Los_Angeles", trigger="report"
    )
    assert "🕒" in text  # a "when is this report" line
    assert "PDT" in text or "PST" in text


def test_render_includes_price_block() -> None:
    result = BriefingResult(
        has_material_update=True,
        headline="WDC up",
        themes=[BriefingTheme(theme="WDC", direction="bullish", insight="up", tickers=["WDC"])],
    )
    text = render_briefing(
        result, generated_at=NOW, timezone="America/Los_Angeles", prices=[_snap("WDC")]
    )
    assert "💵" in text
    assert "WDC: $65.20 (live)" in text
    assert "open $64.10" in text


def test_render_prices_show_even_on_quiet_report() -> None:
    # A focused /report on a quiet day should still show the price.
    result = BriefingResult(has_material_update=False)
    text = render_briefing(
        result, generated_at=NOW, timezone="America/Los_Angeles",
        subject="WDC", prices=[_snap("WDC")],
    )
    assert "backdrop holds" in text.lower()
    assert "WDC: $65.20" in text


# --- run_report integration ------------------------------------------------


class _FakeAnalyst:
    def __init__(self, result: BriefingResult) -> None:
        self.result = result

    async def analyze(self, retrieval, *, prior_themes=None, focus=None):
        return self.result


class _FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> None:
        self.sent.append(text)


class _FakePriceClient(PriceClient):
    def __init__(self) -> None:
        self.asked: list[str] = []

    async def latest_price(self, ticker):
        return None

    async def change_today(self, ticker):
        return None

    async def snapshot(self, ticker):
        self.asked.append(ticker)
        return _snap(ticker)


def _retrieval() -> RetrievalResult:
    art = NewsArticle(
        source="Test", title="WDC", url="https://e.com/x",
        published_at=NOW - timedelta(hours=2), collected_at=NOW, content_hash="h",
    )
    item = assess_freshness(art, now=NOW, window_hours=48)
    return RetrievalResult(now=NOW, window_hours=48, fresh=[item], unverified=[], collected=1, stale_dropped=0)


async def test_focused_report_prices_the_target_ticker() -> None:
    result = BriefingResult(
        has_material_update=True, headline="Western Digital (WDC)",
        themes=[BriefingTheme(theme="WDC", direction="bullish", insight="up")],
    )
    prices = _FakePriceClient()
    notifier = _FakeNotifier()
    run = await run_report(
        "wdc",
        settings=Settings(_env_file=None, price_features_enabled=True),
        analyst=_FakeAnalyst(result),
        notifier=notifier,
        retrieval=_retrieval(),
        memory=None,
        price_client=prices,
    )
    assert run.sent
    assert prices.asked == ["WDC"]  # priced the focused ticker
    assert "WDC: $65.20 (live)" in notifier.sent[0]
    assert "🕒" in notifier.sent[0]  # timestamp present


async def test_prices_skipped_when_feature_disabled() -> None:
    result = BriefingResult(has_material_update=True, headline="x",
                            themes=[BriefingTheme(theme="WDC", direction="bullish", insight="up")])
    prices = _FakePriceClient()
    notifier = _FakeNotifier()
    await run_report(
        "wdc",
        settings=Settings(_env_file=None, briefing_prices_in_report=False),
        analyst=_FakeAnalyst(result), notifier=notifier,
        retrieval=_retrieval(), memory=None, price_client=prices,
    )
    assert prices.asked == []  # no price lookups
    assert "💵" not in notifier.sent[0]
