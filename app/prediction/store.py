"""Storage for user-written prediction strategies.

A strategy is the natural-language lens the AI reasons through (see
`strategies.py`). The built-in default ships in code; anything the user writes
lives here, in a small JSON file alongside the watchlist and runtime prefs.

Two rules shape the design:

- **Ids are forever.** Recorded predictions carry `strategy_id`, so an id must
  never be reused or silently vanish — otherwise past accuracy would be
  misattributed. Deleting therefore *archives*: the strategy leaves the picker
  but its id and name survive so the accuracy screen can still label old calls.
- **User text reaches the model.** It is capped and stripped of control
  characters here; the analyst's guardrails separately instruct the model to
  ignore anything in the STRATEGY block that tries to change its rules.

Mirrors :mod:`app.prefs`: an ``lru_cache``d loader cleared on every write, with
the same EXDEV-safe atomic write for Docker bind mounts.
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from app.config import Settings, get_settings
from app.prediction.strategies import DEFAULT_STRATEGY, Strategy
from app.prefs import get_str, set_str

logger = logging.getLogger("stockpulse.prediction.store")

MAX_NAME_CHARS = 60
MAX_BODY_CHARS = 2000
MIN_BODY_CHARS = 20

_ACTIVE_KEY = "active_strategy_id"
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class StrategyError(ValueError):
    """A strategy could not be saved (bad input, or unknown/immutable id)."""


def _clean(text: str) -> str:
    """Strip control characters and collapse runaway whitespace."""
    text = unicodedata.normalize("NFC", text or "")
    text = _CONTROL_CHARS.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def validate(name: str, body: str) -> tuple[str, str]:
    """Clean and check user input, or raise StrategyError."""
    name, body = _clean(name), _clean(body)
    if not name:
        raise StrategyError("Give the strategy a name.")
    if len(name) > MAX_NAME_CHARS:
        raise StrategyError(f"Name is too long (max {MAX_NAME_CHARS} characters).")
    if len(body) < MIN_BODY_CHARS:
        raise StrategyError(
            f"Describe the strategy in at least {MIN_BODY_CHARS} characters."
        )
    if len(body) > MAX_BODY_CHARS:
        raise StrategyError(f"Strategy is too long (max {MAX_BODY_CHARS} characters).")
    return name, body


@lru_cache
def _load(path: str) -> dict:
    file = Path(path)
    if not file.exists():
        return {}
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read strategies file '%s': %s. Ignoring.", file, exc)
        return {}
    return data if isinstance(data, dict) else {}


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


def _path(settings: Settings | None = None) -> Path:
    return Path((settings or get_settings()).strategies_file)


def _records(settings: Settings | None = None) -> dict[str, dict]:
    raw = _load(str(_path(settings))).get("strategies")
    return raw if isinstance(raw, dict) else {}


def _to_strategy(record: dict) -> Strategy:
    """A stored record as the Strategy the analyst consumes.

    User text has no translation, so `display()` shows it exactly as written
    whatever the UI language — their words, not a machine rendering of them.
    """
    return Strategy(
        id=str(record.get("id")),
        name=str(record.get("name") or "Untitled"),
        body=str(record.get("body") or ""),
        builtin=False,
    )


def _new_id(existing: dict[str, dict]) -> str:
    """A short, permanent id. Never reused — old predictions still point at it."""
    while True:
        candidate = f"s_{uuid.uuid4().hex[:8]}"
        if candidate not in existing:
            return candidate


# --- reads -----------------------------------------------------------------


def list_strategies(
    settings: Settings | None = None, *, include_archived: bool = False
) -> list[Strategy]:
    """The built-in default first, then the user's own (newest last)."""
    records = _records(settings)
    custom = [
        r
        for r in records.values()
        if include_archived or not r.get("archived")
    ]
    custom.sort(key=lambda r: str(r.get("created_at") or ""))
    return [DEFAULT_STRATEGY, *(_to_strategy(r) for r in custom)]


def get_strategy(strategy_id: str, settings: Settings | None = None) -> Strategy | None:
    """Look up any strategy by id, archived ones included — the accuracy screen
    still needs to name the lens behind an old prediction."""
    if not strategy_id or strategy_id == DEFAULT_STRATEGY.id:
        return DEFAULT_STRATEGY
    record = _records(settings).get(strategy_id)
    return _to_strategy(record) if record else None


def get_active_strategy(settings: Settings | None = None) -> Strategy:
    """The strategy new predictions should use. Falls back to the built-in
    default if the active one was archived or the file went missing."""
    settings = settings or get_settings()
    active_id = get_str(_ACTIVE_KEY, settings)
    if not active_id:
        return DEFAULT_STRATEGY
    record = _records(settings).get(active_id)
    if record is None or record.get("archived"):
        return DEFAULT_STRATEGY
    return _to_strategy(record)


# --- writes ----------------------------------------------------------------


def create_strategy(
    name: str, body: str, *, settings: Settings | None = None
) -> Strategy:
    name, body = validate(name, body)
    settings = settings or get_settings()
    path = _path(settings)
    data = dict(_load(str(path)))
    records = dict(data.get("strategies") or {})

    strategy_id = _new_id(records)
    records[strategy_id] = {
        "id": strategy_id,
        "name": name,
        "body": body,
        "archived": False,
        "created_at": datetime.now(tz=UTC).isoformat(),
    }
    data["strategies"] = records
    _write(data, path)
    _load.cache_clear()
    logger.info("Created strategy %s (%s).", strategy_id, name)
    return _to_strategy(records[strategy_id])


def update_strategy(
    strategy_id: str, *, name: str, body: str, settings: Settings | None = None
) -> Strategy:
    name, body = validate(name, body)
    settings = settings or get_settings()
    if strategy_id == DEFAULT_STRATEGY.id:
        raise StrategyError("The built-in strategy can't be edited.")

    path = _path(settings)
    data = dict(_load(str(path)))
    records = dict(data.get("strategies") or {})
    record = records.get(strategy_id)
    if record is None:
        raise StrategyError("That strategy no longer exists.")

    # Editing rewrites the lens but keeps the id, so past predictions stay
    # attributed to it. That's a deliberate trade: heavy edits blur history.
    records[strategy_id] = {**record, "name": name, "body": body}
    data["strategies"] = records
    _write(data, path)
    _load.cache_clear()
    return _to_strategy(records[strategy_id])


def archive_strategy(strategy_id: str, *, settings: Settings | None = None) -> None:
    """Retire a strategy. Kept (not deleted) so old predictions stay labelled."""
    settings = settings or get_settings()
    if strategy_id == DEFAULT_STRATEGY.id:
        raise StrategyError("The built-in strategy can't be removed.")

    path = _path(settings)
    data = dict(_load(str(path)))
    records = dict(data.get("strategies") or {})
    record = records.get(strategy_id)
    if record is None:
        raise StrategyError("That strategy no longer exists.")

    records[strategy_id] = {**record, "archived": True}
    data["strategies"] = records
    _write(data, path)
    _load.cache_clear()

    # Don't leave the picker pointing at something the user just retired.
    if get_str(_ACTIVE_KEY, settings) == strategy_id:
        set_str(_ACTIVE_KEY, DEFAULT_STRATEGY.id, path=settings.prefs_file)
    logger.info("Archived strategy %s.", strategy_id)


def set_active_strategy(strategy_id: str, *, settings: Settings | None = None) -> Strategy:
    """Choose which strategy new predictions use."""
    settings = settings or get_settings()
    strategy = get_strategy(strategy_id, settings)
    if strategy is None:
        raise StrategyError("That strategy no longer exists.")
    if strategy_id != DEFAULT_STRATEGY.id and _records(settings)[strategy_id].get("archived"):
        raise StrategyError("That strategy has been removed.")
    set_str(_ACTIVE_KEY, strategy_id, path=settings.prefs_file)
    return strategy


__all__ = [
    "MAX_BODY_CHARS",
    "MAX_NAME_CHARS",
    "MIN_BODY_CHARS",
    "StrategyError",
    "archive_strategy",
    "create_strategy",
    "get_active_strategy",
    "get_strategy",
    "list_strategies",
    "set_active_strategy",
    "update_strategy",
    "validate",
]
