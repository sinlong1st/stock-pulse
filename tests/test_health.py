"""Phase 0 smoke tests: the app starts and the health endpoint responds."""

from fastapi.testclient import TestClient

from app import __version__
from app.config import Settings
from app.main import app


def test_health_endpoint_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_watchlist_parses_comma_separated_string() -> None:
    settings = Settings(watchlist="nvda, amd ,pltr")
    assert settings.watchlist == ["NVDA", "AMD", "PLTR"]
