"""Tests for /language: supported-set gate + live persistence of the choice."""

import json

from app.commands import build_command_handlers
from app.commands.language import cmd_language
from app.config import Settings
from app.prefs import SUPPORTED_LANGUAGES, resolve_language, set_language


def _settings(tmp_path):
    return Settings(
        _env_file=None,
        output_language="English",
        prefs_file=str(tmp_path / "runtime_prefs.json"),
    )


# --- prefs store -----------------------------------------------------------


def test_supported_languages() -> None:
    assert SUPPORTED_LANGUAGES == {"en": "English", "vi": "Vietnamese"}


def test_resolve_language_defaults_to_env(tmp_path) -> None:
    # No prefs file yet → fall back to OUTPUT_LANGUAGE.
    assert resolve_language(_settings(tmp_path)) == "English"


def test_set_and_resolve_roundtrip(tmp_path) -> None:
    settings = _settings(tmp_path)
    set_language("Vietnamese", path=settings.prefs_file)
    assert resolve_language(settings) == "Vietnamese"
    # Persisted to disk.
    saved = json.loads((tmp_path / "runtime_prefs.json").read_text(encoding="utf-8"))
    assert saved["language"] == "Vietnamese"


def test_set_language_falls_back_when_rename_fails(tmp_path, monkeypatch) -> None:
    import app.prefs as prefs_mod

    settings = _settings(tmp_path)

    def _cross_device(src, dst):  # simulate a Docker single-file bind mount
        raise OSError("EXDEV: cross-device link")

    monkeypatch.setattr(prefs_mod.os, "replace", _cross_device)
    set_language("Vietnamese", path=settings.prefs_file)
    assert resolve_language(settings) == "Vietnamese"  # direct-write fallback worked


# --- /language command -----------------------------------------------------


async def test_cmd_language_shows_current_and_options_when_empty(tmp_path) -> None:
    reply = await cmd_language("", language="English", path=str(tmp_path / "p.json"))
    assert "Current language: English" in reply
    assert "en (English)" in reply and "vi (Vietnamese)" in reply


async def test_cmd_language_rejects_unsupported(tmp_path) -> None:
    reply = await cmd_language("fr", language="English", path=str(tmp_path / "p.json"))
    assert "isn't supported" in reply
    assert "en (English)" in reply and "vi (Vietnamese)" in reply
    # Nothing was written.
    assert not (tmp_path / "p.json").exists()


async def test_cmd_language_sets_vietnamese(tmp_path) -> None:
    path = str(tmp_path / "p.json")
    reply = await cmd_language("vi", language="English", path=path)
    assert "Đã đổi ngôn ngữ sang Vietnamese" in reply  # confirmed in the new language
    saved = json.loads((tmp_path / "p.json").read_text(encoding="utf-8"))
    assert saved["language"] == "Vietnamese"


async def test_cmd_language_sets_english(tmp_path) -> None:
    path = str(tmp_path / "p.json")
    set_language("Vietnamese", path=path)  # start in VN
    reply = await cmd_language("en", language="Vietnamese", path=path)
    assert "Language set to English" in reply


def test_flag_get_set_roundtrip(tmp_path) -> None:
    from app.prefs import get_flag, set_flag

    s = Settings(_env_file=None, prefs_file=str(tmp_path / "p.json"))
    assert get_flag("telegram_enabled", True, s) is True  # default when unset
    set_flag("telegram_enabled", False, path=s.prefs_file)
    assert get_flag("telegram_enabled", True, s) is False


def test_registry_includes_language_command() -> None:
    async def report_handler(args):
        return None

    handlers = build_command_handlers(
        Settings(_env_file=None, briefing_command="/report"), report_handler=report_handler
    )
    assert {"/language", "/watch", "/unwatch", "/watchlist", "/help", "/report"} <= set(handlers)
