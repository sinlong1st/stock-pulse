"""Phase 0 smoke tests: the app starts and the health endpoint responds."""

from fastapi.testclient import TestClient

from app import __version__
from app.main import app


def test_health_endpoint_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}
