"""Thin rolling memory of recent briefing themes (Briefing plan, step G).

The briefing's news source is always live, but "is this trend strengthening or
fading?" needs a little continuity. This keeps the last few hours of themes in
a small JSON file so each run can feed PRIOR_THEMES to the analyst — and so a
storyline already reported isn't re-announced as brand new.

Deliberately a file, not a DB table: it's mutable runtime state for a
single-user local service, so it needs no migration. Corrupt/missing files
degrade gracefully to "no prior context".
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.briefing.models import BriefingResult

logger = logging.getLogger("stockpulse.briefing.memory")


class ThemeMemory:
    """A rolling window of recent briefing themes, persisted to a JSON file."""

    def __init__(
        self, path: str | Path, *, memory_hours: float = 3.0, max_entries: int = 50
    ) -> None:
        self.path = Path(path)
        self.memory_hours = memory_hours
        self.max_entries = max_entries

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Briefing memory file unreadable; ignoring: %s", self.path)
            return []
        return data if isinstance(data, list) else []

    def _save(self, entries: list[dict]) -> None:
        try:
            payload = json.dumps(entries, ensure_ascii=False, indent=2)
            self.path.write_text(payload, encoding="utf-8")
        except OSError:
            logger.warning("Could not write briefing memory file: %s", self.path)

    @staticmethod
    def _parse_at(entry: dict) -> datetime | None:
        try:
            dt = datetime.fromisoformat(entry["at"])
        except (KeyError, ValueError, TypeError):
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)

    def _recent_entries(self, now: datetime) -> list[dict]:
        cutoff = now - timedelta(hours=self.memory_hours)
        out = []
        for entry in self._load():
            at = self._parse_at(entry)
            if at is not None and at >= cutoff:
                out.append(entry)
        return out

    def recent_theme_lines(self, now: datetime | None = None) -> list[str]:
        """Prompt-ready lines for PRIOR_THEMES, most recent first, deduped.

        e.g. "AI & semiconductors (bullish, strengthening)".
        """
        now = now or datetime.now(tz=UTC)
        seen: set[str] = set()
        lines: list[str] = []
        for entry in reversed(self._recent_entries(now)):  # newest first
            for theme in entry.get("themes", []):
                label = str(theme.get("theme", "")).strip()
                if not label or label.lower() in seen:
                    continue
                seen.add(label.lower())
                direction = theme.get("direction", "mixed")
                trend = theme.get("trend", "new")
                lines.append(f"{label} ({direction}, {trend})")
        return lines

    def record(self, result: BriefingResult, now: datetime | None = None) -> None:
        """Append this briefing's themes and prune anything outside the window."""
        if not result.themes:
            return
        now = now or datetime.now(tz=UTC)
        entries = self._recent_entries(now)  # already-pruned survivors
        entries.append(
            {
                "at": now.isoformat(timespec="minutes"),
                "headline": result.headline,
                "themes": [
                    {
                        "theme": t.theme,
                        "direction": t.direction,
                        "trend": t.trend,
                        "freshness": t.freshness,
                    }
                    for t in result.themes
                ],
            }
        )
        self._save(entries[-self.max_entries :])
