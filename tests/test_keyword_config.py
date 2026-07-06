"""Tests for loading the configurable keywords file (macro + sectors)."""

import json

from app.keyword_config import load_keywords
from app.pipeline.keywords import DEFAULT_MACRO_KEYWORDS, DEFAULT_SECTOR_KEYWORDS


def test_loads_macro_and_sectors(tmp_path) -> None:
    file = tmp_path / "keywords.json"
    file.write_text(
        json.dumps({"macro": ["Fed", "CPI"], "sectors": {"Crypto": ["bitcoin"]}}),
        encoding="utf-8",
    )
    config = load_keywords(file)
    assert config.macro == ["Fed", "CPI"]
    assert config.sectors == {"Crypto": ["bitcoin"]}


def test_missing_macro_key_keeps_default_macro(tmp_path) -> None:
    file = tmp_path / "keywords.json"
    file.write_text(json.dumps({"sectors": {"Crypto": ["bitcoin"]}}), encoding="utf-8")
    config = load_keywords(file)
    assert config.macro == list(DEFAULT_MACRO_KEYWORDS)  # default kept
    assert config.sectors == {"Crypto": ["bitcoin"]}


def test_empty_sectors_disables_sectors(tmp_path) -> None:
    file = tmp_path / "keywords.json"
    file.write_text(json.dumps({"macro": ["Fed"], "sectors": {}}), encoding="utf-8")
    config = load_keywords(file)
    assert config.sectors == {}


def test_missing_file_falls_back_to_defaults(tmp_path) -> None:
    config = load_keywords(tmp_path / "nope.json")
    assert config.macro == list(DEFAULT_MACRO_KEYWORDS)
    assert set(config.sectors) == set(DEFAULT_SECTOR_KEYWORDS)


def test_invalid_json_falls_back_to_defaults(tmp_path) -> None:
    file = tmp_path / "keywords.json"
    file.write_text("{ not valid ", encoding="utf-8")
    config = load_keywords(file)
    assert config.macro == list(DEFAULT_MACRO_KEYWORDS)
