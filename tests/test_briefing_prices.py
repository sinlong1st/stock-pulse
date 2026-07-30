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

    async def analyze(self, retrieval, *, prior_themes=None, focus=None, price_moves=None):
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


def test_full_report_prices_whole_watchlist(monkeypatch) -> None:
    from app.jobs import briefing as bmod
    from app.watchlist import WatchlistConfig

    wl = WatchlistConfig(tickers=("NVDA", "MSFT", "WDC"), aliases={})
    monkeypatch.setattr(bmod, "get_watchlist_config", lambda: wl)

    tickers = bmod._price_tickers(Settings(_env_file=None), None)
    assert set(tickers) == {"NVDA", "MSFT", "WDC"}  # whole watchlist priced

    # Display order leads with the ticker the AI mentioned.
    result = BriefingResult(
        has_material_update=True,
        headline="MSFT",
        themes=[BriefingTheme(theme="MSFT", direction="bullish", insight="x", tickers=["MSFT"])],
    )
    snaps = [PriceSnapshot(t, 1.0, None, None, None) for t in ("NVDA", "MSFT", "WDC")]
    ordered = bmod._order_for_display(snaps, result)
    assert ordered[0].ticker == "MSFT"


def test_format_price_moves_filters_by_threshold() -> None:
    from app.jobs.briefing import _format_price_moves

    snaps = [
        PriceSnapshot("MU", 90.0, NOW, 100.0, 100.0),  # -10% -> included
        PriceSnapshot("WDC", 104.0, NOW, 100.0, 100.0),  # +4% -> included
        PriceSnapshot("NVDA", 101.0, NOW, 100.0, 100.0),  # +1% -> below 3% threshold
    ]
    moves = _format_price_moves(snaps, 3.0)
    assert "MU -10.0%" in moves
    assert "WDC +4.0%" in moves
    assert "NVDA" not in moves


class _MoverCapturingAnalyst:
    def __init__(self) -> None:
        self.price_moves_seen = None

    async def analyze(self, retrieval, *, prior_themes=None, focus=None, price_moves=None):
        self.price_moves_seen = price_moves
        return BriefingResult(has_material_update=True, headline="x")


async def test_movers_are_fed_to_the_analyst() -> None:
    analyst = _MoverCapturingAnalyst()
    mover = _FakePriceClient()
    # WDC moves +2.7% from prev close (65.2 vs 63.5) -> below default 3% by a hair;
    # use a lower threshold so it registers.
    await run_report(
        "wdc",
        settings=Settings(
            _env_file=None, price_features_enabled=True, briefing_price_move_threshold_pct=1.0
        ),
        analyst=analyst,
        notifier=_FakeNotifier(),
        retrieval=_retrieval(),
        memory=None,
        price_client=mover,
    )
    assert analyst.price_moves_seen and "WDC" in analyst.price_moves_seen


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
