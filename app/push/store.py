"""Persistent store of registered Expo push tokens (single-user MVP).

Modeled on :mod:`app.prefs` / :mod:`app.watchlist`: a small JSON file (a list of
tokens), an ``lru_cache``d loader cleared on every write, and an EXDEV-safe
write (atomic rename, direct-write fallback for Docker single-file bind mounts).
"""

import json
import logging
import os
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger("stockpulse.push.store")


@lru_cache
def _load(path: str) -> tuple[str, ...]:
    file = Path(path)
    if not file.exists():
        return ()
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read push tokens '%s': %s. Ignoring.", file, exc)
        return ()
    if not isinstance(data, list):
        return ()
    return tuple(str(t) for t in data if isinstance(t, str) and t.strip())


def list_tokens(settings=None) -> list[str]:
    settings = settings or get_settings()
    return list(_load(str(settings.push_tokens_file)))


def add_token(token: str, *, path: str | Path | None = None) -> bool:
    """Register a token. Returns False if it was already present."""
    path = Path(path or get_settings().push_tokens_file)
    tokens = list(_load(str(path)))
    if token in tokens:
        return False
    tokens.append(token)
    _write(tokens, path)
    _load.cache_clear()
    logger.info("Registered a push token (%d total).", len(tokens))
    return True


def remove_token(token: str, *, path: str | Path | None = None) -> bool:
    """Unregister a token. Returns False if it wasn't present."""
    path = Path(path or get_settings().push_tokens_file)
    tokens = list(_load(str(path)))
    if token not in tokens:
        return False
    _write([t for t in tokens if t != token], path)
    _load.cache_clear()
    return True


def _write(tokens: list[str], path: Path) -> None:
    content = json.dumps(tokens, ensure_ascii=False, indent=2)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)  # atomic on a normal filesystem
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        path.write_text(content, encoding="utf-8")
