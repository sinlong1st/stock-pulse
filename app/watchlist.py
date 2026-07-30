"""Load the configurable watchlist from a JSON file.

The watchlist maps each ticker symbol to a list of company-name aliases,
so both live in one editable file (``watchlist.json``) instead of code.
If the file is missing or invalid, built-in defaults are used so the app
keeps working.

File format (``watchlist.json``)::

    {
      "NVDA": ["Nvidia"],
      "MSFT": ["Microsoft"],
      "MU":   ["Micron", "Micron Technology"]
    }

A ticker with no aliases can use an empty list: ``"TSLA": []``.
"""

import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import get_settings
from app.pipeline.keywords import DEFAULT_COMPANY_ALIASES

logger = logging.getLogger("stockpulse.watchlist")


@dataclass(frozen=True)
class WatchlistConfig:
    """Resolved watchlist: the tickers to track and their name aliases."""

    tickers: tuple[str, ...]
    aliases: dict[str, list[str]]


def _defaults() -> WatchlistConfig:
    return WatchlistConfig(
        tickers=tuple(DEFAULT_COMPANY_ALIASES.keys()),
        aliases={ticker: list(names) for ticker, names in DEFAULT_COMPANY_ALIASES.items()},
    )


def load_watchlist(path: str | Path) -> WatchlistConfig:
    """Load a watchlist config from ``path``, falling back to defaults."""
    file = Path(path)
    if not file.exists():
        logger.warning("Watchlist file '%s' not found; using built-in defaults.", file)
        return _defaults()

    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Could not read watchlist file '%s': %s. Using defaults.", file, exc)
        return _defaults()

    if not isinstance(raw, dict):
        logger.error(
            "Watchlist file '%s' must be a JSON object of TICKER -> [names]. Using defaults.",
            file,
        )
        return _defaults()

    tickers: list[str] = []
    aliases: dict[str, list[str]] = {}
    for ticker, names in raw.items():
        symbol = str(ticker).strip().upper()
        if not symbol:
            continue
        tickers.append(symbol)
        if isinstance(names, list):
            aliases[symbol] = [str(name).strip() for name in names if str(name).strip()]
        else:
            aliases[symbol] = []

    if not tickers:
        logger.warning("Watchlist file '%s' had no tickers; using built-in defaults.", file)
        return _defaults()

    logger.info("Loaded %d watchlist tickers from '%s'.", len(tickers), file)
    return WatchlistConfig(tickers=tuple(tickers), aliases=aliases)


@lru_cache
def get_watchlist_config() -> WatchlistConfig:
    """Return the process-wide watchlist config (cached)."""
    return load_watchlist(get_settings().watchlist_file)


def _write_watchlist(config: WatchlistConfig, path: str | Path) -> None:
    """Write the watchlist to ``path`` atomically (temp file then rename)."""
    path = Path(path)
    data = {ticker: config.aliases.get(ticker, []) for ticker in config.tickers}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def add_ticker(
    symbol: str, aliases: list[str] | None = None, *, path: str | Path | None = None
) -> bool:
    """Add a ticker to the watchlist file. Returns False if already present."""
    path = path or get_settings().watchlist_file
    config = load_watchlist(path)
    symbol = symbol.strip().upper()
    if symbol in config.tickers:
        return False
    new_aliases = dict(config.aliases)
    new_aliases[symbol] = aliases or []
    _write_watchlist(WatchlistConfig(tuple(config.tickers) + (symbol,), new_aliases), path)
    get_watchlist_config.cache_clear()
    logger.info("Added %s to the watchlist.", symbol)
    return True


def watchlist_file_is_empty(path: str | Path | None = None) -> bool:
    """True if the watchlist file exists but holds no tickers.

    (The loader then falls back to built-in defaults — useful to warn about.)
    """
    file = Path(path or get_settings().watchlist_file)
    if not file.exists():
        return False
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return isinstance(data, dict) and not data


def remove_ticker(symbol: str, *, path: str | Path | None = None) -> bool:
    """Remove a ticker from the watchlist file. Returns False if not present."""
    path = path or get_settings().watchlist_file
    config = load_watchlist(path)
    symbol = symbol.strip().upper()
    if symbol not in config.tickers:
        return False
    new_tickers = tuple(t for t in config.tickers if t != symbol)
    new_aliases = {t: v for t, v in config.aliases.items() if t != symbol}
    _write_watchlist(WatchlistConfig(new_tickers, new_aliases), path)
    get_watchlist_config.cache_clear()
    logger.info("Removed %s from the watchlist.", symbol)
    return True
