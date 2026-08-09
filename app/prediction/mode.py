"""Which analyst(s) a prediction runs through.

Three modes, chosen by the user in the app and persisted like the language and
active-strategy prefs:

    openai    — one read, the fastest and cheapest option
    deepseek  — one read from the other model
    both      — two independent reads of the same evidence (the default)

`both` is the default deliberately. It is the only mode that produces *paired*
samples — same stock, same evidence, same minute — and pairing is what makes the
per-provider accuracy comparison mean anything. Single-model runs spread across
different stocks and different days mostly compare the stocks.

A mode is a *request*, not a guarantee. Keys come and go (a blank
DEEPSEEK_API_KEY, a revoked one), so `plan()` reconciles what was asked for
against what is actually configured and always returns something runnable — the
user gets a prediction, plus a note when they didn't get the one they picked.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings, get_settings
from app.llm import available_providers
from app.prefs import get_str, set_str

MODES = ("openai", "deepseek", "both")

_PREF_KEY = "prediction_analysis_mode"


@dataclass(frozen=True)
class AnalysisPlan:
    """Who will actually run, after reconciling the request with the keys."""

    requested: str  # what the user asked for
    primary: str  # the provider whose read is the headline
    second: str | None  # the second opinion, or None for a single read

    @property
    def effective(self) -> str:
        return "both" if self.second else self.primary

    @property
    def downgraded(self) -> bool:
        """True when we could not honour the request (a key is missing)."""
        return self.effective != self.requested

    def as_dict(self) -> dict:
        return {
            "requested": self.requested,
            "effective": self.effective,
            "primary": self.primary,
            "second": self.second,
            "downgraded": self.downgraded,
        }


def normalize(value: str | None) -> str | None:
    """A recognised mode, or None. Unknown values are rejected, not guessed at."""
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower()
    return candidate if candidate in MODES else None


def resolve_mode(settings: Settings | None = None) -> str:
    """The user's saved choice, else the env default, else `both`."""
    settings = settings or get_settings()
    return (
        normalize(get_str(_PREF_KEY, settings))
        or normalize(settings.prediction_analysis_mode)
        or "both"
    )


def set_mode(value: str, *, path=None) -> str:
    """Persist a mode. Raises ValueError on anything unrecognised."""
    mode = normalize(value)
    if mode is None:
        raise ValueError(f"Unknown analysis mode {value!r}; expected one of {', '.join(MODES)}")
    set_str(_PREF_KEY, mode, path=path)
    return mode


def plan(settings: Settings | None = None, mode: str | None = None) -> AnalysisPlan | None:
    """Work out who runs. Returns None when no provider is configured at all.

    The fallbacks are deliberately quiet-but-visible: we would rather hand back a
    working prediction from the other model than refuse because the requested one
    has no key. `downgraded` is what tells the app to say so.
    """
    settings = settings or get_settings()
    requested = normalize(mode) or resolve_mode(settings)
    have = available_providers(settings)
    if not have:
        return None

    if requested == "both":
        if len(have) >= 2:
            # OpenAI leads when present: it is the faster of the two, so the
            # headline read lands sooner.
            primary = "openai" if "openai" in have else have[0]
            second = next(p for p in have if p != primary)
            return AnalysisPlan(requested, primary, second)
        # Only one key — a single read is the honest outcome.
        return AnalysisPlan(requested, have[0], None)

    if requested in have:
        return AnalysisPlan(requested, requested, None)

    # Asked for a provider we have no key for: fall back rather than fail.
    return AnalysisPlan(requested, have[0], None)
