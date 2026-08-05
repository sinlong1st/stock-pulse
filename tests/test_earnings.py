"""Tests for the earnings client (Yahoo quoteSummary + crumb handshake).

Yahoo is mocked via an httpx transport — same pattern as the price/news clients.
"""

from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from app.config import Settings
from app.earnings import Earnings, EarningsClient, fetch_many


def _epoch(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())


def _payload(*, next_date: date | None, actual=2.02, estimate=1.89, last=date(2026, 6, 30)):
    calendar = {"earnings": {"earningsDate": [{"raw": _epoch(next_date)}] if next_date else []}}
    history = {
        "history": [
            {
                "quarter": {"raw": _epoch(last)},
                "epsActual": {"raw": actual},
                "epsEstimate": {"raw": estimate},
                "surprisePercent": {"raw": 0.0674},
            }
        ]
    }
    return {"quoteSummary": {"result": [{"calendarEvents": calendar, "earningsHistory": history}]}}


def _transport(handler):
    return httpx.MockTransport(handler)


def _ok_handler(payload, *, crumb="CRUMB123", calls=None):
    def handle(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(request.url))
        path = request.url.path
        if "fc.yahoo.com" in request.url.host:
            return httpx.Response(404, headers={"Set-Cookie": "A1=x; Path=/"})
        if path.endswith("/v1/test/getcrumb"):
            return httpx.Response(200, text=crumb)
        if "/quoteSummary/" in path:
            assert request.url.params.get("crumb") == crumb
            return httpx.Response(200, json=payload)
        return httpx.Response(404)

    return handle


def _client(handler, **kw) -> EarningsClient:
    return EarningsClient(transport=_transport(handler), **kw)


# --- parsing ---------------------------------------------------------------


async def test_fetch_parses_next_date_and_last_quarter() -> None:
    soon = datetime.now(tz=UTC).date() + timedelta(days=10)
    c = _client(_ok_handler(_payload(next_date=soon)))

    got = await c.fetch("AAPL")
    assert got is not None
    assert got.next_date == soon
    assert got.days_until(datetime.now(tz=UTC).date()) == 10
    assert got.eps_actual == 2.02 and got.eps_estimate == 1.89
    assert got.last_date == date(2026, 6, 30)
    assert got.verdict == "beat"


@pytest.mark.parametrize(
    "actual,estimate,expected",
    [(2.02, 1.89, "beat"), (1.50, 2.00, "miss"), (2.00, 2.00, "inline"), (2.00, 2.01, "inline")],
)
async def test_verdict_thresholds(actual, estimate, expected) -> None:
    assert Earnings("X", eps_actual=actual, eps_estimate=estimate).verdict == expected


def test_verdict_none_without_both_numbers() -> None:
    assert Earnings("X", eps_actual=2.0).verdict is None
    assert Earnings("X").verdict is None


def test_as_dict_scales_surprise_to_percent() -> None:
    got = Earnings("X", surprise_pct=0.0674).as_dict()
    assert got["surprisePct"] == 6.7  # 0.0674 -> 6.7%


def test_days_until_counts_from_the_callers_today() -> None:
    """Counting from UTC would read a day short all evening in Pacific."""
    e = Earnings("X", next_date=date(2026, 8, 10))
    assert e.days_until(date(2026, 8, 4)) == 6
    assert e.days_until(date(2026, 8, 10)) == 0
    assert e.days_until(date(2026, 8, 11)) == -1  # already reported
    assert Earnings("X").days_until(date(2026, 8, 4)) is None


async def test_missing_earnings_date_still_returns_history() -> None:
    c = _client(_ok_handler(_payload(next_date=None)))
    got = await c.fetch("AAPL")
    assert got is not None and got.next_date is None and got.eps_actual == 2.02


# --- resilience ------------------------------------------------------------


async def test_401_triggers_one_crumb_refresh_then_succeeds() -> None:
    state = {"served": 0}
    payload = _payload(next_date=date(2026, 10, 29))

    def handle(request: httpx.Request) -> httpx.Response:
        if "fc.yahoo.com" in request.url.host:
            return httpx.Response(404)
        if request.url.path.endswith("/v1/test/getcrumb"):
            return httpx.Response(200, text="FRESH")
        # First quoteSummary call is rejected as if the crumb went stale.
        state["served"] += 1
        if state["served"] == 1:
            return httpx.Response(401, text="Invalid Cookie")
        return httpx.Response(200, json=payload)

    got = await _client(handle).fetch("AAPL")
    assert got is not None and got.next_date == date(2026, 10, 29)
    assert state["served"] == 2  # retried exactly once


async def test_crumb_failure_returns_none_not_raise() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    assert await _client(handle).fetch("AAPL") is None


async def test_implausible_crumb_is_rejected() -> None:
    """A login/consent page instead of a token must not be used as a crumb."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/v1/test/getcrumb"):
            return httpx.Response(200, text="<!DOCTYPE html><html>consent required</html>")
        return httpx.Response(404)

    assert await _client(handle).fetch("AAPL") is None


async def test_network_error_returns_none() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    assert await _client(handle).fetch("AAPL") is None


async def test_non_json_body_returns_none() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if "fc.yahoo.com" in request.url.host:
            return httpx.Response(404)
        if request.url.path.endswith("/v1/test/getcrumb"):
            return httpx.Response(200, text="CRUMB123")
        return httpx.Response(200, text="not json")

    assert await _client(handle).fetch("AAPL") is None


# --- caching + fan-out -----------------------------------------------------


async def test_second_fetch_is_served_from_cache() -> None:
    calls: list[str] = []
    c = _client(_ok_handler(_payload(next_date=date(2026, 10, 29)), calls=calls))

    await c.fetch("AAPL")
    summary_calls = [u for u in calls if "quoteSummary" in u]
    await c.fetch("AAPL")
    assert len([u for u in calls if "quoteSummary" in u]) == len(summary_calls) == 1


async def test_cache_expires() -> None:
    calls: list[str] = []
    c = _client(_ok_handler(_payload(next_date=date(2026, 10, 29)), calls=calls), cache_ttl=0)

    await c.fetch("AAPL")
    await c.fetch("AAPL")
    assert len([u for u in calls if "quoteSummary" in u]) == 2


async def test_fetch_many_drops_empty_rows_and_caps() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if "fc.yahoo.com" in request.url.host:
            return httpx.Response(404)
        if request.url.path.endswith("/v1/test/getcrumb"):
            return httpx.Response(200, text="CRUMB123")
        ticker = request.url.path.rsplit("/", 1)[-1]
        if ticker == "EMPTY":  # nothing known -> should not appear in the result
            return httpx.Response(
                200,
                json={"quoteSummary": {"result": [{"calendarEvents": {}, "earningsHistory": {}}]}},
            )
        return httpx.Response(200, json=_payload(next_date=date(2026, 10, 29)))

    settings = Settings(_env_file=None, earnings_max_tickers=2)
    got = await fetch_many(["AAPL", "EMPTY", "MSFT"], settings=settings, client=_client(handle))
    assert "AAPL" in got
    assert "EMPTY" not in got  # dropped: no date, no EPS
    assert "MSFT" not in got  # cut by earnings_max_tickers=2


async def test_fetch_many_disabled_returns_empty() -> None:
    settings = Settings(_env_file=None, earnings_enabled=False)
    assert await fetch_many(["AAPL"], settings=settings) == {}
