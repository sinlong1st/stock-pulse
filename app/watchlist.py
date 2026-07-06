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
