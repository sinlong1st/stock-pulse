"""Tests for AI classification (Phase 4).

The OpenAI API is never called for real: a httpx MockTransport returns
canned responses, so we exercise the request/parse/validate path offline.
"""

import json
from datetime import UTC, datetime

import httpx
import pytest

from app.models.article import NewsArticle
from app.models.classification import ClassificationResult
from app.pipeline.classifier import ClassificationError, OpenAIClassifier


def _article() -> NewsArticle:
    return NewsArticle(
        source="Yahoo Finance",
        title="Fed signals rate cuts may be delayed",
        summary="Powell comments push yields higher.",
        url="https://example.com/fed",
        collected_at=datetime.now(tz=UTC),
        content_hash="h" * 64,
    )


def _openai_response(content: dict | str) -> httpx.Response:
    body = content if isinstance(content, str) else json.dumps(content)
    return httpx.Response(200, json={"choices": [{"message": {"content": body}}]})


def _classifier(handler) -> OpenAIClassifier:
    return OpenAIClassifier(
        "test-key",
        model="gpt-4o-mini",
        watchlist=["NVDA", "AMD"],
        transport=httpx.MockTransport(handler),
    )


# --- ClassificationResult validation --------------------------------------


def test_result_normalizes_case_and_tickers() -> None:
    result = ClassificationResult.model_validate(
        {
            "is_market_relevant": True,
            "importance": "high",
            "category": "macro",
            "sentiment": "positive",
            "related_tickers": ["nvda", " amd "],
            "summary": "s",
            "why_it_matters": "w",
            "should_alert": True,
            "confidence": 1.5,
        }
    )
    assert result.importance == "HIGH"
    assert result.category == "MACRO"
    assert result.sentiment == "BULLISH"  # synonym normalized
    assert result.related_tickers == ["NVDA", "AMD"]
    assert result.confidence == 1.0  # clamped


def test_sentiment_defaults_to_neutral_and_maps_synonyms() -> None:
    base = {
        "is_market_relevant": True,
        "importance": "LOW",
        "category": "OTHER",
        "summary": "s",
        "why_it_matters": "w",
        "should_alert": False,
    }
    assert ClassificationResult.model_validate(base).sentiment == "NEUTRAL"  # default
    assert ClassificationResult.model_validate({**base, "sentiment": "DOWN"}).sentiment == "BEARISH"
    assert ClassificationResult.model_validate({**base, "sentiment": "bull"}).sentiment == "BULLISH"


def test_result_rejects_invalid_importance() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ClassificationResult.model_validate(
            {
                "is_market_relevant": True,
                "importance": "SUPER",
                "category": "MACRO",
                "summary": "s",
                "why_it_matters": "w",
                "should_alert": True,
            }
        )


# --- OpenAIClassifier ------------------------------------------------------


async def test_classify_returns_validated_result() -> None:
    payload = {
        "is_market_relevant": True,
        "importance": "HIGH",
        "category": "MACRO",
        "related_tickers": ["QQQ", "NVDA"],
        "summary": "Fed may delay cuts.",
        "why_it_matters": "Higher-for-longer pressures tech.",
        "should_alert": True,
        "confidence": 0.9,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers["Authorization"] == "Bearer test-key"
        return _openai_response(payload)

    result = await _classifier(handler).classify(_article())
    assert result.importance == "HIGH"
    assert result.should_alert is True
    assert result.related_tickers == ["QQQ", "NVDA"]


async def test_classify_includes_language_instruction() -> None:
    payload = {
        "is_market_relevant": True,
        "importance": "MEDIUM",
        "category": "MACRO",
        "related_tickers": [],
        "summary": "s",
        "why_it_matters": "w",
        "should_alert": True,
        "confidence": 0.5,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        assert "Vietnamese" in body  # language instruction is sent
        return _openai_response(payload)

    classifier = OpenAIClassifier(
        "test-key",
        watchlist=["NVDA"],
        language="Vietnamese",
        transport=httpx.MockTransport(handler),
    )
    await classifier.classify(_article())


async def test_classify_raises_on_invalid_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _openai_response("this is not json")

    with pytest.raises(ClassificationError):
        await _classifier(handler).classify(_article())


async def test_classify_raises_on_schema_violation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _openai_response({"importance": "HIGH"})  # missing required fields

    with pytest.raises(ClassificationError):
        await _classifier(handler).classify(_article())


async def test_classify_raises_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    with pytest.raises(ClassificationError):
        await _classifier(handler).classify(_article())


def test_build_classifier_without_key_raises() -> None:
    with pytest.raises(ClassificationError):
        OpenAIClassifier("", watchlist=[])


# --- Storage ---------------------------------------------------------------


@pytest.fixture
def session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.database import Base

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        yield s


def test_classification_repository_add_and_dedupe(session) -> None:
    from app.db.repository import ArticleRepository, ClassificationRepository

    article_repo = ArticleRepository(session)
    row = article_repo.add(_article())
    session.commit()

    result = ClassificationResult(
        is_market_relevant=True,
        importance="HIGH",
        category="MACRO",
        related_tickers=["NVDA"],
        summary="s",
        why_it_matters="w",
        should_alert=True,
        confidence=0.8,
    )
    class_repo = ClassificationRepository(session)
    class_repo.add(row.id, result, model="gpt-4o-mini")
    session.commit()

    assert class_repo.exists_for(row.id) is True
    assert class_repo.classified_article_ids([row.id]) == {row.id}
