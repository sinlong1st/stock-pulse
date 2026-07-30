"""Tests for focused single-stock reports (/report WDC, /report micosoft)."""

from datetime import UTC, datetime, timedelta

from app.briefing.analyst import build_system_prompt, build_user_message
from app.briefing.focus import (
    build_focus_collectors,
    parse_focus,
    resolve_focus,
)
from app.briefing.models import BriefingResult, BriefingTheme
from app.briefing.retrieval import RetrievalResult, assess_freshness
from app.config import Settings
from app.jobs.briefing import run_report
from app.models.article import NewsArticle
from app.watchlist import WatchlistConfig

NOW = datetime(2026, 7, 28, 16, 0, tzinfo=UTC)

WL = WatchlistConfig(
    tickers=("NVDA", "MSFT", "WDC", "SPCX"),
    aliases={
        "NVDA": ["Nvidia"],
        "MSFT": ["Microsoft"],
        "WDC": ["Western Digital"],
        "SPCX": ["SpaceX"],
    },
)


# --- parsing ---------------------------------------------------------------


def test_parse_focus() -> None:
    assert parse_focus("/report wdc", "/report") == "wdc"
    assert parse_focus("/report Western Digital", "/report") == "Western Digital"
    assert parse_focus("/report@StockPulseBot spacex", "/report") == "spacex"
    assert parse_focus("/report", "/report") is None
    assert parse_focus("/report   ", "/report") is None


# --- resolution (the "common sense" for retrieval) -------------------------


def test_resolve_exact_ticker() -> None:
    t = resolve_focus("wdc", WL)
    assert t.ticker == "WDC"
    assert t.name == "Western Digital"


def test_resolve_company_alias() -> None:
    t = resolve_focus("microsoft", WL)
    assert t.ticker == "MSFT"
    assert t.search_term == "Microsoft"


def test_resolve_typo_ticker() -> None:
    t = resolve_focus("wdcc", WL)  # typo
    assert t.ticker == "WDC"


def test_resolve_typo_company() -> None:
    t = resolve_focus("micosoft", WL)  # typo
    assert t.ticker == "MSFT"


def test_resolve_spacex_alias() -> None:
    t = resolve_focus("spacex", WL)
    assert t.ticker == "SPCX"


def test_resolve_unknown_falls_back_to_free_text() -> None:
    t = resolve_focus("some random thing", WL)
    assert t.ticker is None
    assert t.search_term == "some random thing"
    assert t.subject_label == "SOME RANDOM THING"


def test_describe_hint_for_prompt() -> None:
    assert "WDC" in resolve_focus("wdcc", WL).describe
    assert "Western Digital" in resolve_focus("wdcc", WL).describe


# --- collectors ------------------------------------------------------------


def test_focus_collectors_with_ticker_has_yahoo_and_google() -> None:
    target = resolve_focus("wdc", WL)
    cols = build_focus_collectors(target, Settings(_env_file=None))
    names = [c.source_name for c in cols]
    assert "Yahoo Finance" in names and "Google News" in names


def test_focus_collectors_freetext_google_only() -> None:
    target = resolve_focus("obscure co", WL)
    cols = build_focus_collectors(target, Settings(_env_file=None))
    assert [c.source_name for c in cols] == ["Google News"]


# --- prompt carries focus --------------------------------------------------


def test_system_prompt_focus_block() -> None:
    p = build_system_prompt(
        watchlist=["WDC"], now=NOW, window_hours=48, language="English",
        focus='"wdcc" (looks like Western Digital / WDC)',
    )
    assert "FOCUS MODE" in p
    assert "Western Digital" in p


def test_user_message_focus_line() -> None:
    art = NewsArticle(
        source="Test", title="x", url="https://e.com/x",
        published_at=NOW - timedelta(minutes=10), collected_at=NOW, content_hash="h",
    )
    item = assess_freshness(art, now=NOW, window_hours=48)
    retrieval = RetrievalResult(
        now=NOW, window_hours=48, fresh=[item], unverified=[], collected=1, stale_dropped=0
    )
    msg = build_user_message(retrieval, focus='"wdc" (looks like WDC)')
    assert "FOCUS REQUEST" in msg


# --- run_report integration ------------------------------------------------


class _FakeAnalyst:
    def __init__(self, result: BriefingResult) -> None:
        self.result = result
        self.focus_seen = None

    async def analyze(self, retrieval, *, prior_themes=None, focus=None, price_moves=None):
        self.focus_seen = focus
        return self.result


class _FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> None:
        self.sent.append(text)


def _retrieval() -> RetrievalResult:
    art = NewsArticle(
        source="Test", title="WDC guides higher", url="https://e.com/x",
        published_at=NOW - timedelta(hours=3), collected_at=NOW, content_hash="h",
    )
    item = assess_freshness(art, now=NOW, window_hours=48)
    return RetrievalResult(
        now=NOW, window_hours=48, fresh=[item], unverified=[], collected=1, stale_dropped=0
    )


async def test_run_report_focus_passes_focus_and_subject() -> None:
    analyst = _FakeAnalyst(
        BriefingResult(
            has_material_update=True, headline="Western Digital (WDC) update",
            themes=[BriefingTheme(theme="WDC", direction="bullish", insight="up")],
        )
    )
    notifier = _FakeNotifier()
    run = await run_report(
        "wdc",
        analyst=analyst,
        notifier=notifier,
        retrieval=_retrieval(),
        memory=None,
    )
    assert run.sent
    assert analyst.focus_seen and "WDC" in analyst.focus_seen  # focus reached the analyst
    assert "WDC" in notifier.sent[0]  # subject in the title


async def test_run_report_no_query_is_full_briefing() -> None:
    analyst = _FakeAnalyst(BriefingResult(has_material_update=False))
    notifier = _FakeNotifier()
    run = await run_report(
        None, analyst=analyst, notifier=notifier, retrieval=_retrieval(), memory=None
    )
    assert run.sent  # always answers
    assert analyst.focus_seen is None  # no focus -> normal watchlist briefing
