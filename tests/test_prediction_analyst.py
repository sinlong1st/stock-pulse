"""Tests for the prediction analyst: model validation + layered prompt + parsing."""

import json

import httpx
import pytest

from app.prediction.analyst import PredictionAnalyst, PredictionError, _user_message
from app.prediction.models import PredictionRead
from app.prediction.signals import Signals
from app.prediction.strategies import DEFAULT_STRATEGY, Strategy

_SIGNALS = Signals(
    range_low=100.0,
    range_high=200.0,
    discount_level="cheap",
    range_note="5% above the 6-month low, 45% below the high",
    discount_note="Near the lower third of its 6-month range.",
    trend="down",
    enough_history=True,
)


# --- model validation ------------------------------------------------------


def test_prediction_read_normalizes_synonyms() -> None:
    r = PredictionRead.model_validate(
        {
            "horizons": [
                {"horizon": "1w", "lean": "UP", "confidence": "med", "rationale": "x"},
                {"horizon": "1mo", "lean": "bearish", "confidence": "hi", "rationale": "y"},
                {"horizon": "3mo", "lean": "sideways", "confidence": "low", "rationale": "z"},
            ],
            "drivers": ["  news  ", "", "trend"],
        }
    )
    assert [h.lean for h in r.horizons] == ["bounce", "dip", "hold"]
    assert [h.confidence for h in r.horizons] == ["medium", "high", "low"]
    assert r.drivers == ["news", "trend"]  # blank dropped, trimmed


# --- layered prompt --------------------------------------------------------


def test_user_message_layers_strategy_facts_news() -> None:
    msg = _user_message(
        ticker="WDC",
        name="Western Digital",
        price=120.0,
        signals=_SIGNALS,
        support={"near": 110.0, "long": 100.0},
        news_lines=["Nvidia deal", "Memory prices firm"],
        horizons=["1w", "1mo", "3mo"],
        strategy=Strategy(id="x", name="X", body="MY CUSTOM STRATEGY"),
    )
    assert "STRATEGY" in msg and "MY CUSTOM STRATEGY" in msg
    assert "FACTS (authoritative)" in msg and "cheap" in msg and "down" in msg
    assert "Nvidia deal" in msg
    assert "near $110.00" in msg and "long-term $100.00" in msg
    assert "1w, 1mo, 3mo" in msg


# --- analyst call (mocked OpenAI) ------------------------------------------


def _openai_response(obj: dict) -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"content": json.dumps(obj)}}]}
    )


async def test_analyze_parses_and_validates() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _openai_response(
            {
                "horizons": [
                    {"horizon": "1w", "lean": "bounce", "confidence": "low", "rationale": "a"},
                    {"horizon": "1mo", "lean": "hold", "confidence": "medium", "rationale": "b"},
                ],
                "drivers": ["cheap vs range", "downtrend"],
            }
        )

    analyst = PredictionAnalyst("k", transport=httpx.MockTransport(handler))
    read = await analyst.analyze(
        ticker="WDC", name="Western Digital", signals=_SIGNALS,
        news_lines=["headline"], horizons=["1w", "1mo"], strategy=DEFAULT_STRATEGY,
    )
    assert isinstance(read, PredictionRead)
    assert read.horizons[0].lean == "bounce"
    # guardrails present in the system message
    system = captured["body"]["messages"][0]["content"]
    assert "AUTHORITATIVE" in system and "not investment advice" in system.lower()


async def test_analyze_raises_on_bad_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

    analyst = PredictionAnalyst("k", transport=httpx.MockTransport(handler))
    with pytest.raises(PredictionError):
        await analyst.analyze(
            ticker="WDC", name="WD", signals=_SIGNALS, news_lines=[], horizons=["1w"],
        )
