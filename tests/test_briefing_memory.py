"""Tests for the rolling theme memory (Briefing plan, step G)."""

from datetime import UTC, datetime, timedelta

from app.briefing.memory import ThemeMemory
from app.briefing.models import BriefingResult, BriefingTheme
from app.briefing.retrieval import RetrievalResult, assess_freshness
from app.config import Settings
from app.jobs.briefing import run_briefing
from app.models.article import NewsArticle

NOW = datetime(2026, 7, 28, 16, 0, tzinfo=UTC)


def _result(theme: str, direction: str = "bullish", trend: str = "new") -> BriefingResult:
    return BriefingResult(
        has_material_update=True,
        headline=f"{theme} moving",
        themes=[BriefingTheme(theme=theme, direction=direction, insight="why", trend=trend)],
    )


def test_record_and_recall_roundtrip(tmp_path) -> None:
    mem = ThemeMemory(tmp_path / "mem.json", memory_hours=3)
    mem.record(_result("AI & semiconductors", trend="strengthening"), NOW)

    lines = mem.recent_theme_lines(NOW + timedelta(minutes=30))
    assert lines == ["AI & semiconductors (bullish, strengthening)"]


def test_old_entries_fall_out_of_window(tmp_path) -> None:
    mem = ThemeMemory(tmp_path / "mem.json", memory_hours=2)
    mem.record(_result("Old story"), NOW - timedelta(hours=5))
    mem.record(_result("Fresh story"), NOW - timedelta(minutes=30))

    lines = mem.recent_theme_lines(NOW)
    assert lines == ["Fresh story (bullish, new)"]


def test_recent_themes_dedupe_keep_newest(tmp_path) -> None:
    mem = ThemeMemory(tmp_path / "mem.json", memory_hours=6)
    mem.record(_result("AI", trend="new"), NOW - timedelta(hours=2))
    mem.record(_result("AI", trend="strengthening"), NOW - timedelta(minutes=10))

    lines = mem.recent_theme_lines(NOW)
    assert lines == ["AI (bullish, strengthening)"]  # newest wins, no dup


def test_corrupt_file_degrades_gracefully(tmp_path) -> None:
    path = tmp_path / "mem.json"
    path.write_text("not json{", encoding="utf-8")
    mem = ThemeMemory(path, memory_hours=3)
    assert mem.recent_theme_lines(NOW) == []  # no crash


def test_quiet_result_is_not_recorded(tmp_path) -> None:
    mem = ThemeMemory(tmp_path / "mem.json", memory_hours=3)
    mem.record(BriefingResult(has_material_update=False), NOW)  # no themes
    assert mem.recent_theme_lines(NOW) == []


# --- integration with run_briefing -----------------------------------------


class _CapturingAnalyst:
    def __init__(self, result: BriefingResult) -> None:
        self.result = result
        self.prior_themes_seen: list[str] | None = None

    async def analyze(self, retrieval, *, prior_themes=None, focus=None, price_moves=None):
        self.prior_themes_seen = prior_themes
        return self.result


def _retrieval() -> RetrievalResult:
    art = NewsArticle(
        source="Test", title="x", url="https://e.com/x",
        published_at=NOW - timedelta(minutes=15), collected_at=NOW, content_hash="h",
    )
    item = assess_freshness(art, now=NOW, window_hours=2)
    return RetrievalResult(now=NOW, window_hours=2, fresh=[item], unverified=[], collected=1, stale_dropped=0)


async def test_run_briefing_feeds_and_updates_memory(tmp_path) -> None:
    mem = ThemeMemory(tmp_path / "mem.json", memory_hours=6)
    settings = Settings(_env_file=None)

    # First run records "AI & semiconductors".
    a1 = _CapturingAnalyst(_result("AI & semiconductors", trend="new"))
    await run_briefing(
        trigger="report", settings=settings, analyst=a1,
        notifier=None, deliver=False, retrieval=_retrieval(), memory=mem,
    )
    assert a1.prior_themes_seen == []  # nothing yet on the first run

    # Second run should SEE the theme from the first as prior context.
    a2 = _CapturingAnalyst(_result("Macro", trend="new"))
    await run_briefing(
        trigger="report", settings=settings, analyst=a2,
        notifier=None, deliver=False, retrieval=_retrieval(), memory=mem,
    )
    assert a2.prior_themes_seen == ["AI & semiconductors (bullish, new)"]
