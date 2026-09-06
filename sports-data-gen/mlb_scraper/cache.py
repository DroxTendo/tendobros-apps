"""The on-disk HTML cache: where `extract` writes and `transform` reads.

The cache is the boundary between the two stages, which is why the path
helpers live here rather than inside either one. `extract` fills it from the
network (slowly, and at ~4GB for four seasons); `transform` reads it back and
never opens a socket, so a re-parse after a parser fix costs nothing but CPU.

Layout, per config.SPORT:

    cache/{sport}/{season}/season_schedule.html   # postseason tagging
    cache/{sport}/{season}/{date}/schedule.html   # that day's games
    cache/{sport}/{season}/{date}/{game_id}.html  # one box score

A date directory holding only schedule.html is a genuine no-games day, not a
partial extract -- a day that was never extracted has no directory at all.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import config


class CacheMissError(Exception):
    """A page transform needs isn't on disk.

    Distinct from http_client.FetchError: nothing failed, the page simply was
    never extracted. Callers leave existing records alone rather than marking
    anything failed over it.
    """


def season_schedule_path(year: int) -> Path:
    return config.CACHE_DIR / config.SPORT / str(year) / "season_schedule.html"


def schedule_path(day: datetime.date) -> Path:
    return config.CACHE_DIR / config.SPORT / str(day.year) / day.isoformat() / "schedule.html"


def boxscore_path(season: int, date: str, game_id: str) -> Path:
    """Keyed off the game's own season/date rather than the day being
    processed, so a suspended game completed later files under its own date
    rather than the date of the schedule page that discovered it."""
    return config.CACHE_DIR / config.SPORT / str(season) / date / f"{game_id}.html"


def read(path: Path) -> str:
    if not path.exists():
        raise CacheMissError(f"not in cache: {relname(path)}")
    return path.read_text(encoding="utf-8")


def relname(path: Path) -> str:
    """Repo-relative form for log messages; falls back to the full path for
    anything outside the project (a tmp dir under test, say)."""
    try:
        return str(path.relative_to(config.PROJECT_ROOT))
    except ValueError:
        return str(path)
