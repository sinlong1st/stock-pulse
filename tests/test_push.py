"""Tests for push: token store, Expo notifier, and the /api/push endpoints."""

import httpx
from fastapi.testclient import TestClient

import app.config as config
import app.main as main
from app.config import Settings
from app.push import store
from app.push.notifier import _EXPO_PUSH_URL, send_push

# --- token store -----------------------------------------------------------


def test_add_list_remove_roundtrip(tmp_path) -> None:
    p = str(tmp_path / "push_tokens.json")
    assert store.add_token("ExponentPushToken[aaa]", path=p) is True
    assert store.add_token("ExponentPushToken[aaa]", path=p) is False  # dupe
    assert store.add_token("ExponentPushToken[bbb]", path=p) is True

    s = Settings(_env_file=None, push_tokens_file=p)
    assert set(store.list_tokens(s)) == {"ExponentPushToken[aaa]", "ExponentPushToken[bbb]"}

    assert store.remove_token("ExponentPushToken[aaa]", path=p) is True
    assert store.remove_token("ExponentPushToken[aaa]", path=p) is False  # gone
    assert store.list_tokens(s) == ["ExponentPushToken[bbb]"]


def test_store_write_falls_back_when_rename_fails(tmp_path, monkeypatch) -> None:
    p = str(tmp_path / "push_tokens.json")

    def _cross_device(src, dst):
        raise OSError("EXDEV")

    monkeypatch.setattr(store.os, "replace", _cross_device)
    assert store.add_token("ExponentPushToken[ccc]", path=p) is True
    s = Settings(_env_file=None, push_tokens_file=p)
    assert store.list_tokens(s) == ["ExponentPushToken[ccc]"]


# --- Expo notifier ---------------------------------------------------------


async def test_send_push_posts_expected_payload() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        import json as _json

        seen["body"] = _json.loads(request.content)
        return httpx.Response(200, json={"data": []})

    sent = await send_push(
        ["ExponentPushToken[aaa]", "ExponentPushToken[bbb]"],
        title="Hi",
        body="there",
        data={"alertId": 7},
        settings=Settings(_env_file=None),
        transport=httpx.MockTransport(handler),
    )
    assert sent == 2
    assert seen["url"] == _EXPO_PUSH_URL
    assert seen["body"][0]["to"] == "ExponentPushToken[aaa]"
    assert seen["body"][0]["title"] == "Hi"
    assert seen["body"][0]["data"] == {"alertId": 7}


async def test_send_push_no_tokens_is_noop() -> None:
    assert await send_push([], title="x", body="y", settings=Settings(_env_file=None)) == 0


async def test_send_push_swallows_errors() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    sent = await send_push(
        ["ExponentPushToken[aaa]"],
        title="x",
        body="y",
        settings=Settings(_env_file=None),
        transport=httpx.MockTransport(boom),
    )
    assert sent == 0  # never raises


# --- endpoints -------------------------------------------------------------


def _client(monkeypatch, *, enabled=True, token="s3cret") -> TestClient:
    monkeypatch.setenv("MOBILE_API_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("MOBILE_API_TOKEN", token)
    config.get_settings.cache_clear()
    return TestClient(main.app)


def test_push_register_and_unregister(monkeypatch) -> None:
    monkeypatch.setattr(main, "add_token", lambda t: True)
    monkeypatch.setattr(main, "remove_token", lambda t: True)
    with _client(monkeypatch) as client:
        h = {"Authorization": "Bearer s3cret"}
        reg = client.post("/api/push/register", json={"token": "ExponentPushToken[z]"}, headers=h)
        assert reg.status_code == 200 and reg.json() == {"registered": True, "new": True}

        unreg = client.post(
            "/api/push/unregister", json={"token": "ExponentPushToken[z]"}, headers=h
        )
        assert unreg.status_code == 200 and unreg.json()["removed"] is True

        assert client.post("/api/push/register", json={"token": "x"}).status_code == 401
    config.get_settings.cache_clear()


def test_push_test_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(main, "list_tokens", lambda settings: ["ExponentPushToken[z]"])

    async def fake_send(tokens, **kwargs):
        return len(tokens)

    monkeypatch.setattr(main, "send_push", fake_send)
    with _client(monkeypatch) as client:
        res = client.post("/api/push/test", headers={"Authorization": "Bearer s3cret"})
        assert res.status_code == 200 and res.json() == {"tokens": 1, "sent": 1}
    config.get_settings.cache_clear()
