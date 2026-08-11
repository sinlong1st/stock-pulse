"""Storage for the user's saved positions.

Exit-advisor plan Phase 3. The spec treats every exit analysis as a stateless
request carrying ticker, shares and average cost. That is correct as an API and
wrong as a product: this is a feature you'd use on the same three or four
holdings every day, and a form you retype each time is a form you stop opening.

Two rules shape the design, both inherited from `app.prediction.store`:

- **Ids are forever.** A saved analysis will reference `position_id`, so an id
  must never be reused or silently vanish. Deleting therefore *archives*: the
  position leaves the list but its id survives so past analyses stay attributed.
- **Validation happens here, once.** Shares and average cost go through
  `math.parse_position`, so the store and the analysis can never disagree about
  what a valid position is.

Note what is deliberately *not* stored: `userQuestion` from spec §4. That is a
property of one request, not of the holding.

Mirrors :mod:`app.prefs`: an ``lru_cache``d loader cleared on every write, with
the same EXDEV-safe atomic write for Docker bind mounts.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from app.config import Settings, get_settings
from app.position.math import Position, PositionError, parse_position, parse_price

logger = logging.getLogger("stockpulse.position.store")

# §4's enumerations, with the spec's stated defaults.
INVESTMENT_STYLES = ("short-swing", "swing", "position", "long-term")
RISK_TOLERANCES = ("conservative", "moderate", "aggressive")
DEFAULT_STYLE = "swing"
DEFAULT_RISK = "moderate"

MAX_POSITIONS = 50  # a personal holdings list, not a fund's book

# Letters, digits, dots and dashes — `BRK.B` and `RDS-A` are real holdings. The
# leading character is deliberately not `^`: `^VIX` and friends are indices, and
# an index is not something anyone can hold shares of.
_TICKER = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$")


class PositionStoreError(ValueError):
    """A position could not be saved (bad input, or an unknown id)."""


@dataclass(frozen=True)
class SavedPosition:
    """One holding, as stored. Money stays Decimal until the payload boundary."""

    id: str
    ticker: str
    shares: Decimal
    average_cost: Decimal
    purchase_date: str | None
    stop: Decimal | None
    target: Decimal | None
    investment_style: str
    risk_tolerance: str
    allow_partial_sell: bool
    archived: bool
    created_at: str
    updated_at: str

    def to_position(self) -> Position:
        """The validated value object the math module works in."""
        return Position(shares=self.shares, average_cost=self.average_cost)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "shares": float(self.shares),
            "averageCost": float(self.average_cost),
            "purchaseDate": self.purchase_date,
            "stop": float(self.stop) if self.stop is not None else None,
            "target": float(self.target) if self.target is not None else None,
            "investmentStyle": self.investment_style,
            "riskTolerance": self.risk_tolerance,
            "allowPartialSell": self.allow_partial_sell,
            "archived": self.archived,
            "createdAt": self.created_at,
            # The app shows this as "last confirmed". A position the user sold
            # months ago and never removed would otherwise keep drawing confident
            # advice about shares they don't own.
            "updatedAt": self.updated_at,
        }


# --- validation ------------------------------------------------------------


def clean_ticker(value: str) -> str:
    """Uppercase and check the symbol. Rejects anything that couldn't be one."""
    ticker = (value or "").strip().upper()
    if not _TICKER.match(ticker):
        raise PositionStoreError("That doesn't look like a ticker symbol.")
    return ticker


def _optional_price(value: object, *, field: str) -> Decimal | None:
    """A price that may be absent. Present-but-unusable is still an error —
    a stop of 0 is a typo, not an intention."""
    if value is None or value == "":
        return None
    return parse_price(value, field=field)


def _choice(value: object, allowed: tuple[str, ...], default: str, *, field: str) -> str:
    if value is None or value == "":
        return default
    got = str(value).strip().lower()
    if got not in allowed:
        raise PositionStoreError(f"{field} must be one of: {', '.join(allowed)}.")
    return got


def _clean_date(value: object) -> str | None:
    """An ISO date, or None. Stored as text — it is only ever displayed and
    compared, never used in arithmetic."""
    if value is None or value == "":
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError as exc:
        raise PositionStoreError("Purchase date must be a date like 2026-08-10.") from exc


# --- file plumbing ---------------------------------------------------------


@lru_cache
def _load(path: str) -> dict:
    file = Path(path)
    if not file.exists():
        return {}
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read positions file '%s': %s. Ignoring.", file, exc)
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
    return Path((settings or get_settings()).positions_file)


def _records(settings: Settings | None = None) -> dict[str, dict]:
    raw = _load(str(_path(settings))).get("positions")
    return raw if isinstance(raw, dict) else {}


def _to_position(record: dict) -> SavedPosition:
    """A stored record as a `SavedPosition`.

    Tolerant on read: a hand-edited or older file shouldn't take the whole list
    down, so missing optional fields fall back to the §4 defaults.
    """
    def money(key: str) -> Decimal | None:
        raw = record.get(key)
        return Decimal(str(raw)) if raw is not None else None

    return SavedPosition(
        id=str(record.get("id")),
        ticker=str(record.get("ticker") or ""),
        shares=Decimal(str(record.get("shares") or 0)),
        average_cost=Decimal(str(record.get("average_cost") or 0)),
        purchase_date=record.get("purchase_date"),
        stop=money("stop"),
        target=money("target"),
        investment_style=str(record.get("investment_style") or DEFAULT_STYLE),
        risk_tolerance=str(record.get("risk_tolerance") or DEFAULT_RISK),
        allow_partial_sell=bool(record.get("allow_partial_sell", True)),
        archived=bool(record.get("archived")),
        created_at=str(record.get("created_at") or ""),
        updated_at=str(record.get("updated_at") or record.get("created_at") or ""),
    )


def _new_id(existing: dict[str, dict]) -> str:
    """A short, permanent id. Never reused — past analyses still point at it."""
    while True:
        candidate = f"p_{uuid.uuid4().hex[:8]}"
        if candidate not in existing:
            return candidate


def validate_fields(
    *,
    ticker: str,
    shares: object,
    average_cost: object,
    purchase_date: object = None,
    stop: object = None,
    target: object = None,
    investment_style: object = None,
    risk_tolerance: object = None,
    allow_partial_sell: object = None,
) -> dict:
    """Validate one position's worth of user input into a storable record.

    Public because the Exit Advisor validates unsaved, one-off positions through
    it too — an inline request must never be accepted where a saved one would be
    refused.

    Shares and average cost go through the math module's own validation, so a
    position that can be saved is always a position that can be analyzed.

    Every `PositionError` the math module raises is re-raised as a
    `PositionStoreError`, because that is the only exception the endpoints
    translate into a 400 — leaking the other type would turn a typo in the stop
    field into a 500.
    """
    try:
        position = parse_position(shares=shares, average_cost=average_cost)
        return {
            "ticker": clean_ticker(ticker),
            "shares": str(position.shares),
            "average_cost": str(position.average_cost),
            "purchase_date": _clean_date(purchase_date),
            "stop": _str_or_none(_optional_price(stop, field="stop")),
            "target": _str_or_none(_optional_price(target, field="target")),
            "investment_style": _choice(
                investment_style, INVESTMENT_STYLES, DEFAULT_STYLE, field="investmentStyle"
            ),
            "risk_tolerance": _choice(
                risk_tolerance, RISK_TOLERANCES, DEFAULT_RISK, field="riskTolerance"
            ),
            # §4's default: partial selling is allowed unless the user says so.
            "allow_partial_sell": (
                True if allow_partial_sell is None else bool(allow_partial_sell)
            ),
        }
    except PositionStoreError:
        raise
    except PositionError as exc:  # same failure, the store's exception type
        raise PositionStoreError(str(exc)) from exc


def _str_or_none(value: Decimal | None) -> str | None:
    """Money is stored as a string so JSON can't round-trip it through a float."""
    return str(value) if value is not None else None


# --- reads -----------------------------------------------------------------


def list_positions(
    settings: Settings | None = None, *, include_archived: bool = False
) -> list[SavedPosition]:
    """The user's holdings, oldest first."""
    records = [
        r
        for r in _records(settings).values()
        if include_archived or not r.get("archived")
    ]
    records.sort(key=lambda r: str(r.get("created_at") or ""))
    return [_to_position(r) for r in records]


def get_position(position_id: str, settings: Settings | None = None) -> SavedPosition | None:
    """Look up a position by id, archived ones included — a past analysis still
    needs to name the holding it was about."""
    record = _records(settings).get(position_id)
    return _to_position(record) if record else None


# --- writes ----------------------------------------------------------------


def create_position(
    *, settings: Settings | None = None, **fields: object
) -> SavedPosition:
    """Save a new holding. See `_record_from` for the accepted fields."""
    settings = settings or get_settings()
    path = _path(settings)
    data = dict(_load(str(path)))
    records = dict(data.get("positions") or {})

    live = sum(1 for r in records.values() if not r.get("archived"))
    if live >= MAX_POSITIONS:
        raise PositionStoreError(f"You can save at most {MAX_POSITIONS} positions.")

    now = datetime.now(tz=UTC).isoformat()
    position_id = _new_id(records)
    records[position_id] = {
        **validate_fields(**fields),  # type: ignore[arg-type]
        "id": position_id,
        "archived": False,
        "created_at": now,
        "updated_at": now,
    }
    data["positions"] = records
    _write(data, path)
    _load.cache_clear()
    logger.info("Saved position %s (%s).", position_id, records[position_id]["ticker"])
    return _to_position(records[position_id])


def update_position(
    position_id: str, *, settings: Settings | None = None, **fields: object
) -> SavedPosition:
    """Rewrite a holding, keeping its id.

    `updated_at` moves, which is what the app shows as "last confirmed" — the
    honest signal that a position may be stale is when the user last touched it.
    """
    settings = settings or get_settings()
    path = _path(settings)
    data = dict(_load(str(path)))
    records = dict(data.get("positions") or {})
    record = records.get(position_id)
    if record is None:
        raise PositionStoreError("That position no longer exists.")

    records[position_id] = {
        **record,
        **validate_fields(**fields),  # type: ignore[arg-type]
        "id": position_id,
        "updated_at": datetime.now(tz=UTC).isoformat(),
    }
    data["positions"] = records
    _write(data, path)
    _load.cache_clear()
    return _to_position(records[position_id])


def archive_position(position_id: str, *, settings: Settings | None = None) -> None:
    """Remove a holding from the list. Archived, not deleted, so any analysis
    that referenced it stays attributable."""
    settings = settings or get_settings()
    path = _path(settings)
    data = dict(_load(str(path)))
    records = dict(data.get("positions") or {})
    record = records.get(position_id)
    if record is None:
        raise PositionStoreError("That position no longer exists.")

    records[position_id] = {
        **record,
        "archived": True,
        "updated_at": datetime.now(tz=UTC).isoformat(),
    }
    data["positions"] = records
    _write(data, path)
    _load.cache_clear()
    logger.info("Archived position %s.", position_id)


__all__ = [
    "INVESTMENT_STYLES",
    "MAX_POSITIONS",
    "RISK_TOLERANCES",
    "PositionStoreError",
    "SavedPosition",
    "archive_position",
    "clean_ticker",
    "create_position",
    "get_position",
    "list_positions",
    "update_position",
    "validate_fields",
]
