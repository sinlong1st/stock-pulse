"""Load configurable macro/sector keywords from a JSON file.

Mirrors app.watchlist: macro keywords and sector keyword groups live in an
editable ``keywords.json`` instead of code. If the file is missing or
invalid, built-in defaults are used so the app keeps working.

File format (``keywords.json``)::

    {
      "macro": ["Federal Reserve", "CPI", "tariff"],
      "sectors": {
        "AI/Semiconductor": ["AI", "semiconductor", "GPU"],
        "Crypto": ["bitcoin", "ethereum"]
      }
    }

Either top-level key may be omitted to keep the built-in default for that
part; provide an empty list/object to intentionally disable it.
"""

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import get_settings
from app.pipeline.keywords import DEFAULT_MACRO_KEYWORDS, DEFAULT_SECTOR_KEYWORDS

logger = logging.getLogger("stockpulse.keywords")


@dataclass(frozen=True)
class KeywordConfig:
    """Resolved keyword configuration for the rule filter."""

    macro: list[str]
    sectors: dict[str, list[str]]


def _defaults() -> KeywordConfig:
    return KeywordConfig(
        macro=list(DEFAULT_MACRO_KEYWORDS),
        sectors={sector: list(words) for sector, words in DEFAULT_SECTOR_KEYWORDS.items()},
    )


def _clean_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def load_keywords(path: str | Path) -> KeywordConfig:
    """Load macro/sector keywords from ``path``, falling back to defaults."""
    file = Path(path)
    if not file.exists():
        logger.warning("Keywords file '%s' not found; using built-in defaults.", file)
        return _defaults()

    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Could not read keywords file '%s': %s. Using defaults.", file, exc)
        return _defaults()

    if not isinstance(raw, dict):
        logger.error(
            "Keywords file '%s' must be a JSON object with 'macro'/'sectors'. Using defaults.",
            file,
        )
        return _defaults()

    defaults = _defaults()
    macro = _clean_list(raw["macro"]) if "macro" in raw else defaults.macro

    if "sectors" in raw and isinstance(raw["sectors"], dict):
        sectors = {
            str(name).strip(): _clean_list(words)
            for name, words in raw["sectors"].items()
            if str(name).strip()
        }
    elif "sectors" in raw:
        sectors = {}
    else:
        sectors = defaults.sectors

    logger.info(
        "Loaded %d macro keywords and %d sector groups from '%s'.",
        len(macro),
        len(sectors),
        file,
    )
    return KeywordConfig(macro=macro, sectors=sectors)


@lru_cache
def get_keyword_config() -> KeywordConfig:
    """Return the process-wide keyword config (cached)."""
    return load_keywords(get_settings().keywords_file)
