"""Tests for the alerts page rendering (Phase 6)."""

from datetime import UTC, datetime

from app.db.repository import AlertView
from app.web.views import render_alerts_page


def _view(status: str, *, error: str | None = None) -> AlertView:
    return AlertView(
        id=1,
        article_title="Fed signals rate cuts",
        url="https://example.com/fed",
        importance="HIGH",
        channel="telegram",
        status=status,
        created_at=datetime.now(tz=UTC),
        sent_at=datetime.now(tz=UTC) if status == "SENT" else None,
        error_message=error,
    )


def test_renders_alert_rows_with_status_and_counts() -> None:
    html = render_alerts_page([_view("PENDING"), _view("SENT")])
    assert "status-PENDING" in html
    assert "status-SENT" in html
    assert "Fed signals rate cuts" in html
    assert "1 pending" in html
    assert "1 sent" in html


def test_failed_alert_shows_error_escaped() -> None:
    html = render_alerts_page([_view("FAILED", error="<bad> & error")])
    assert "status-FAILED" in html
    assert "&lt;bad&gt; &amp; error" in html
    assert "<bad>" not in html


def test_empty_alerts_shows_message() -> None:
    html = render_alerts_page([])
    assert "No alerts yet" in html
