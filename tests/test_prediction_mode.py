"""Tests for the analysis-mode choice (openai / deepseek / both)."""

import pytest

from app.config import Settings
from app.prediction import mode as mode_mod


def _settings(tmp_path, **kw) -> Settings:
    return Settings(
        _env_file=None,
        prefs_file=str(tmp_path / "prefs.json"),
        **kw,
    )


def _with_providers(monkeypatch, *names):
    monkeypatch.setattr(mode_mod, "available_providers", lambda s: list(names))


# --- normalization ---------------------------------------------------------


def test_normalize_accepts_known_modes() -> None:
    assert mode_mod.normalize("BOTH") == "both"
    assert mode_mod.normalize("  deepseek ") == "deepseek"


def test_normalize_rejects_rather_than_guesses() -> None:
    # A typo must not silently become a mode that spends money on two calls.
    assert mode_mod.normalize("bothh") is None
    assert mode_mod.normalize("gpt-4o") is None
    assert mode_mod.normalize(None) is None


# --- resolution ------------------------------------------------------------


def test_default_is_both(tmp_path) -> None:
    assert mode_mod.resolve_mode(_settings(tmp_path)) == "both"


def test_env_default_applies_when_nothing_saved(tmp_path) -> None:
    settings = _settings(tmp_path, prediction_analysis_mode="openai")
    assert mode_mod.resolve_mode(settings) == "openai"


def test_saved_choice_beats_env(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path, prediction_analysis_mode="openai")
    monkeypatch.setattr(mode_mod, "get_str", lambda key, s=None: "deepseek")
    assert mode_mod.resolve_mode(settings) == "deepseek"


def test_a_corrupt_saved_value_falls_back(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mode_mod, "get_str", lambda key, s=None: "nonsense")
    assert mode_mod.resolve_mode(_settings(tmp_path)) == "both"


def test_set_mode_rejects_unknown(tmp_path) -> None:
    with pytest.raises(ValueError):
        mode_mod.set_mode("claude", path=tmp_path / "prefs.json")


def test_set_mode_round_trips(tmp_path) -> None:
    prefs = tmp_path / "prefs.json"
    assert mode_mod.set_mode("deepseek", path=prefs) == "deepseek"
    assert mode_mod.resolve_mode(_settings(tmp_path)) == "deepseek"


# --- planning: what actually runs ------------------------------------------


def test_both_runs_two_with_openai_leading(tmp_path, monkeypatch) -> None:
    _with_providers(monkeypatch, "openai", "deepseek")
    got = mode_mod.plan(_settings(tmp_path), mode="both")
    # OpenAI leads because it is the faster of the two.
    assert (got.primary, got.second) == ("openai", "deepseek")
    assert got.effective == "both" and not got.downgraded


def test_single_mode_runs_only_that_model(tmp_path, monkeypatch) -> None:
    _with_providers(monkeypatch, "openai", "deepseek")
    got = mode_mod.plan(_settings(tmp_path), mode="deepseek")
    assert (got.primary, got.second) == ("deepseek", None)
    assert not got.downgraded


def test_both_with_one_key_degrades_to_a_single_read(tmp_path, monkeypatch) -> None:
    _with_providers(monkeypatch, "openai")
    got = mode_mod.plan(_settings(tmp_path), mode="both")
    assert (got.primary, got.second) == ("openai", None)
    assert got.downgraded  # the app should say so rather than pretend


def test_asking_for_an_unconfigured_model_falls_back(tmp_path, monkeypatch) -> None:
    # No DeepSeek key: give them a working prediction from the model we do have,
    # flagged as downgraded, rather than an error.
    _with_providers(monkeypatch, "openai")
    got = mode_mod.plan(_settings(tmp_path), mode="deepseek")
    assert (got.primary, got.second) == ("openai", None)
    assert got.requested == "deepseek" and got.downgraded


def test_no_providers_at_all_is_none(tmp_path, monkeypatch) -> None:
    _with_providers(monkeypatch)
    assert mode_mod.plan(_settings(tmp_path), mode="both") is None


def test_both_leads_with_deepseek_when_openai_is_absent(tmp_path, monkeypatch) -> None:
    _with_providers(monkeypatch, "deepseek")
    got = mode_mod.plan(_settings(tmp_path), mode="both")
    assert got.primary == "deepseek" and got.second is None


def test_as_dict_shape(tmp_path, monkeypatch) -> None:
    _with_providers(monkeypatch, "openai", "deepseek")
    payload = mode_mod.plan(_settings(tmp_path), mode="both").as_dict()
    assert payload == {
        "requested": "both",
        "effective": "both",
        "primary": "openai",
        "second": "deepseek",
        "downgraded": False,
    }
