"""Tests for briefing render + the run_briefing job (Briefing plan, step D)."""

from datetime import UTC, datetime, timedelta

from app.briefing.models import BriefingResult, BriefingTheme, WatchlistNote
from app.briefing.render import render_briefing
from app.briefing.retrieval import RetrievalResult, assess_freshness
from app.jobs.briefing import run_briefing, window_for
from app.config import Settings
from app.models.article import NewsArticle

NOW = datetime(2026, 7, 28, 16, 0, tzinfo=UTC)


def _material(urgency: str = "notable") -> BriefingResult:
    return BriefingResult(
        has_material_update=True,
        urgency=urgency,
        headline="AI capex story strengthening",
        themes=[
            BriefingTheme(
                theme="AI & semiconductors",
                direction="bullish",
                tickers=["NVDA"],
                insight="Hyperscaler capex guides higher.",
                trend="strengthening",
                freshness="new",
            )
        ],
        watchlist_notes=[WatchlistNote(ticker="NVDA", note="capex tailwind", direction="bullish")],
        risk_flags=["oil spike on Middle East tensions"],
    )


# --- render ----------------------------------------------------------------


def test_render_material_english() -> None:
    text = render_briefing(_material(), language="English", trigger="report")
    assert "AI & semiconductors" in text
    assert "🟢" in text  # bullish
    assert "NVDA" in text
    assert "not investment advice" in text


def test_render_urgent_flags_top() -> None:
    text = render_briefing(_material("urgent"), language="English", trigger="morning")
    assert "🔴 Urgent:" in text


def test_render_quiet_message() -> None:
    quiet = BriefingResult(has_material_update=False, urgency="routine")
    text = render_briefing(quiet, language="English", trigger="report")
    assert "backdrop holds" in text.lower()


def test_render_vietnamese() -> None:
    text = render_briefing(_material(), language="Vietnamese", trigger="report")
    assert "Báo cáo nhanh" in text
    assert "không phải lời khuyên đầu tư" in text


def test_render_quiet_vietnamese() -> None:
    quiet = BriefingResult(has_material_update=False)
    text = render_briefing(quiet, language="Vietnamese", trigger="wrap")
    assert "bối cảnh giữ nguyên" in text.lower()


# --- job -------------------------------------------------------------------


class _FakeAnalyst:
    def __init__(self, result: BriefingResult) -> None:
        self.result = result
        self.calls = 0

    async def analyze(self, retrieval, *, prior_themes=None, focus=None):
        self.calls += 1
        self.focus_seen = focus
        return self.result


class _FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> None:
        self.sent.append(text)


def _retrieval() -> RetrievalResult:
    art = NewsArticle(
        source="Test", title="Nvidia capex", url="https://e.com/x",
        published_at=NOW - timedelta(minutes=30), collected_at=NOW, content_hash="h",
    )
    item = assess_freshness(art, now=NOW, window_hours=2)
    return RetrievalResult(
        now=NOW, window_hours=2, fresh=[item], unverified=[], collected=1, stale_dropped=0
    )


async def test_run_briefing_sends_material() -> None:
    notifier = _FakeNotifier()
    run = await run_briefing(
        trigger="report",
        settings=Settings(_env_file=None, output_language="English"),
        analyst=_FakeAnalyst(_material()),
        notifier=notifier,
        retrieval=_retrieval(),
    )
    assert run.sent
    assert run.has_material_update
    assert len(notifier.sent) == 1
    assert "AI & semiconductors" in notifier.sent[0]


async def test_on_demand_always_sends_even_when_quiet() -> None:
    notifier = _FakeNotifier()
    quiet = BriefingResult(has_material_update=False)
    run = await run_briefing(
        trigger="report", always_send=True,
        settings=Settings(_env_file=None), analyst=_FakeAnalyst(quiet),
        notifier=notifier, retrieval=_retrieval(),
    )
    assert run.sent  # on-demand answers even on a quiet window
    assert "backdrop holds" in notifier.sent[0].lower()


async def test_intraday_stays_silent_when_not_material() -> None:
    notifier = _FakeNotifier()
    quiet = BriefingResult(has_material_update=False)
    run = await run_briefing(
        trigger="intraday", always_send=False,
        settings=Settings(_env_file=None), analyst=_FakeAnalyst(quiet),
        notifier=notifier, retrieval=_retrieval(),
    )
    assert not run.sent
    assert run.skipped_reason == "no material update"
    assert notifier.sent == []


def test_window_for_uses_settings() -> None:
    s = Settings(_env_file=None)
    assert window_for("morning", s) == s.briefing_morning_window_hours
    assert window_for("intraday", s) == s.briefing_intraday_window_hours
    assert window_for("report", s) == s.briefing_ondemand_window_hours
