"""Runtime user preferences that can be changed live (no restart).

Currently just the output language, switchable from Telegram via /language.
The choice is persisted to a small JSON file (``runtime_prefs.json``) so it
survives restarts and is picked up immediately by alerts + briefings.

Modeled on :mod:`app.watchlist`: an ``lru_cache``d loader that is cleared on
every write, plus an EXDEV-safe write (atomic rename, direct-write fallback for
Docker single-file bind mounts).

Only a small, curated set of languages is supported so the AI output stays
predictable; unknown codes are rejected by the /language command.
"""

import json
import logging
import os
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger("stockpulse.prefs")

# Short code -> canonical language name injected into AI prompts.
SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "vi": "Vietnamese",
}


@lru_cache
def _load(path: str) -> dict:
    """Read the prefs file (cached); returns {} if missing or unreadable."""
    file = Path(path)
    if not file.exists():
        return {}
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read prefs file '%s': %s. Ignoring.", file, exc)
        return {}
    return data if isinstance(data, dict) else {}


def resolve_language(settings=None) -> str:
    """The language AI output should use.

    The saved /language choice if one exists, otherwise the ``OUTPUT_LANGUAGE``
    env default. Safe to call anywhere a language string is needed.
    """
    settings = settings or get_settings()
    saved = _load(str(settings.prefs_file)).get("language")
    if isinstance(saved, str) and saved.strip():
        return saved.strip()
    return settings.output_language


def set_language(name: str, *, path: str | Path | None = None) -> None:
    """Persist the canonical language name and clear the cache so readers see it."""
    path = Path(path or get_settings().prefs_file)
    prefs = dict(_load(str(path)))
    prefs["language"] = name
    _write(prefs, path)
    _load.cache_clear()
    logger.info("Output language set to %s.", name)


def get_flag(key: str, default: bool, settings=None) -> bool:
    """Read a boolean runtime pref, falling back to `default` if unset."""
    settings = settings or get_settings()
    val = _load(str(settings.prefs_file)).get(key)
    return val if isinstance(val, bool) else default


def set_flag(key: str, value: bool, *, path: str | Path | None = None) -> None:
    """Persist a boolean runtime pref and clear the cache."""
    path = Path(path or get_settings().prefs_file)
    prefs = dict(_load(str(path)))
    prefs[key] = bool(value)
    _write(prefs, path)
    _load.cache_clear()
    logger.info("Runtime pref %s set to %s.", key, value)


def get_str(key: str, settings=None) -> str | None:
    """Read a string runtime pref, or None when unset/blank."""
    settings = settings or get_settings()
    val = _load(str(settings.prefs_file)).get(key)
    return val.strip() if isinstance(val, str) and val.strip() else None


def set_str(key: str, value: str, *, path: str | Path | None = None) -> None:
    """Persist a string runtime pref and clear the cache."""
    path = Path(path or get_settings().prefs_file)
    prefs = dict(_load(str(path)))
    prefs[key] = value
    _write(prefs, path)
    _load.cache_clear()
    logger.info("Runtime pref %s set to %r.", key, value)


def telegram_delivery_enabled(settings=None) -> bool:
    """Whether the user wants alerts on Telegram (the app toggle; default on).

    This is only the *preference* — whether Telegram is actually configured
    (creds present / a notifier exists) is checked separately at the send site.
    """
    settings = settings or get_settings()
    return get_flag("telegram_enabled", True, settings)


def push_delivery_enabled(settings=None) -> bool:
    """Whether alerts should push to the app. Defaults to PUSH_ENABLED; the
    app's toggle (runtime pref) overrides."""
    settings = settings or get_settings()
    return get_flag("push_enabled", settings.push_enabled, settings)


def _write(data: dict, path: Path) -> None:
    content = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)  # atomic on a normal filesystem
    except OSError:
        # Single-file bind mount (Docker): rename across filesystems fails.
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        path.write_text(content, encoding="utf-8")
