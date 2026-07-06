"""Tests for loading the configurable watchlist file (Phase 3)."""

import json

from app.pipeline.keywords import DEFAULT_COMPANY_ALIASES
from app.watchlist import load_watchlist


def test_loads_tickers_and_aliases_uppercasing_symbols(tmp_path) -> None:
    file = tmp_path / "watchlist.json"
    file.write_text(json.dumps({"nvda": ["Nvidia"], "MU": ["Micron"]}), encoding="utf-8")

    config = load_watchlist(file)
    assert config.tickers == ("NVDA", "MU")
    assert config.aliases["NVDA"] == ["Nvidia"]
    assert config.aliases["MU"] == ["Micron"]


def test_ticker_with_empty_alias_list_is_allowed(tmp_path) -> None:
    file = tmp_path / "watchlist.json"
    file.write_text(json.dumps({"TSLA": []}), encoding="utf-8")

    config = load_watchlist(file)
    assert config.tickers == ("TSLA",)
    assert config.aliases["TSLA"] == []


def test_missing_file_falls_back_to_defaults(tmp_path) -> None:
    config = load_watchlist(tmp_path / "does_not_exist.json")
    assert set(config.tickers) == set(DEFAULT_COMPANY_ALIASES.keys())


def test_invalid_json_falls_back_to_defaults(tmp_path) -> None:
    file = tmp_path / "watchlist.json"
    file.write_text("{ this is not json ", encoding="utf-8")

    config = load_watchlist(file)
    assert set(config.tickers) == set(DEFAULT_COMPANY_ALIASES.keys())


def test_non_object_json_falls_back_to_defaults(tmp_path) -> None:
    file = tmp_path / "watchlist.json"
    file.write_text(json.dumps(["NVDA", "AMD"]), encoding="utf-8")

    config = load_watchlist(file)
    assert set(config.tickers) == set(DEFAULT_COMPANY_ALIASES.keys())
