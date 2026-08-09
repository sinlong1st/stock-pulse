"""Fixtures that keep the suite hermetic.

A test has to mean the same thing on a laptop and on a bare CI runner. The
watchlist is the one piece of ambient state that quietly broke that rule:
``watchlist.json`` is gitignored, eight modules read it through
``get_watchlist_config()``, and any test that reaches one of them was really
asserting against whatever tickers the developer happened to own.

That is not hypothetical — three focused-report tests passed locally for months
because the author's watchlist had WDC in it, and failed on the first CI run
because the built-in defaults do not.

So every test gets the same small watchlist from ``fixtures/watchlist.json``.
A test that cares about specific tickers should still pass its own
``WatchlistConfig`` explicitly; this fixture only removes the machine from the
equation.
"""

from pathlib import Path

import pytest

from app.config import get_settings
from app.watchlist import get_watchlist_config

_WATCHLIST = Path(__file__).parent / "fixtures" / "watchlist.json"


@pytest.fixture(autouse=True)
def fixed_watchlist(monkeypatch: pytest.MonkeyPatch):
    """Point every test at the fixture watchlist, whatever the machine has.

    An env var rather than a monkeypatched function: modules do
    ``from app.watchlist import get_watchlist_config``, so each holds its own
    reference and patching the original would miss them all. Setting
    WATCHLIST_FILE steers the real loader, which every caller shares.

    Both caches are cleared on the way in *and* out — they are ``lru_cache``d,
    so a value read before this fixture ran would otherwise outlive it and leak
    into the next test.
    """
    monkeypatch.setenv("WATCHLIST_FILE", str(_WATCHLIST))
    get_settings.cache_clear()
    get_watchlist_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_watchlist_config.cache_clear()
