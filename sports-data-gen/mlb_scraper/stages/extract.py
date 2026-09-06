"""Stage 1: the website -> cache/. Downloads, and nothing else.

This stage produces no JSON. It fills the HTML cache and records what it got,
and `transform` turns that into data. Because downloading is all it does,
--force here has exactly one meaning: fetch the page again.

It still parses the day's schedule page, but only to discover which box score
URLs exist -- discovery, not extraction of records. Postseason tagging is
deliberately not done here: this stage downloads season_schedule.html so
transform has a current copy, and never reads it.

Every game commits its own state the instant its page lands, so an interrupted
run loses at most the one download in flight. That matters here and only here:
a lost download costs another 5-7s round trip against a site we're trying to
be a good citizen of.
"""

from __future__ import annotations

import datetime
import logging

import requests

import config
from mlb_scraper import cache, http_client, schedule, state as state_mod

logger = logging.getLogger(__name__)


def _in_season_window(day: datetime.date) -> bool:
    start = datetime.date(day.year, *config.SEASON_START_MONTH_DAY)
    end = datetime.date(day.year, *config.SEASON_END_MONTH_DAY)
    return start <= day <= end


def _iter_dates(start: datetime.date, end: datetime.date):
    current = start
    while current <= end:
        if _in_season_window(current):
            yield current
        current += datetime.timedelta(days=1)


def _download_season_schedule(year: int, session, mode: str) -> None:
    """Always re-downloaded, never read here -- unlike every other page this
    scraper touches, a season's schedule is a moving target until that
    season's postseason is over, so a cached copy would silently miss games
    added later. transform reads whatever this leaves on disk.

    One extra request per season per run, negligible against the per-game
    volume. A failure is only a warning: transform will fall back to the
    previous copy, and refuses to re-tag a season it can't resolve at all.
    """
    url = f"{config.BASE_URL}/leagues/majors/{year}-schedule.shtml"
    try:
        http_client.fetch(url, cache_path=cache.season_schedule_path(year), session=session, mode=http_client.REFETCH)
    except http_client.FetchError as exc:
        logger.warning("could not refresh season schedule for %d, transform will use the cached copy: %s", year, exc)


def _download_game(ref, session, state, redo: bool, mode: str) -> bool:
    """Returns True if the page ended up cached (either just now or already)."""
    existing = state_mod.get_game(state, ref.game_id)
    if not redo and existing and existing.get("extract_status") == "done":
        logger.info("    skipped already downloaded: %s", ref.game_id)
        return True

    logger.info("    downloading game: %s", ref.game_id)
    cache_path = cache.boxscore_path(ref.season, ref.date, ref.game_id)
    attempts = (existing or {}).get("attempts", 0)

    try:
        http_client.fetch(ref.url, cache_path=cache_path, session=session, mode=mode)
    except http_client.FetchError as exc:
        logger.error("game %s failed: %s", ref.game_id, exc)
        state_mod.set_game(
            state, ref.game_id,
            date=ref.date, season=ref.season, home_team=ref.home_code, boxscore_url=ref.url,
            extract_status="failed", extract_error=str(exc), attempts=attempts + 1,
        )
        return False

    state_mod.set_game(
        state, ref.game_id,
        date=ref.date, season=ref.season, home_team=ref.home_code, boxscore_url=ref.url,
        extract_status="done", cache_path=state_mod.relpath(cache_path),
        extracted_at=state_mod.now_iso(), extract_error=None, attempts=attempts,
    )
    return True


def _extract_day(day: datetime.date, session, state, redo: bool, mode: str) -> None:
    date_str = day.isoformat()
    season = day.year

    day_entry = state_mod.get_day(state, date_str)
    if not redo and day_entry and day_entry.get("extract_status") in ("done", "empty"):
        reason = "all games downloaded" if day_entry["extract_status"] == "done" else "no games"
        logger.info("skipping %s, %s", date_str, reason)
        return

    logger.info("downloading %s", date_str)
    schedule_url = f"{config.BASE_URL}/boxes/index.fcgi?year={day.year}&month={day.month}&day={day.day}"
    cache_path = cache.schedule_path(day)

    try:
        html = http_client.fetch(schedule_url, cache_path=cache_path, session=session, mode=mode)
    except http_client.FetchError as exc:
        logger.error("schedule fetch failed for %s: %s", date_str, exc)
        state_mod.set_day(state, date_str, season=season, extract_status="failed", extract_error=str(exc), extract_checked_at=state_mod.now_iso())
        return

    if not schedule.page_matches_date(html, day):
        # Baseball-Reference silently returned a fallback page (someone else's
        # already-completed games, not an honest empty/404) for a date it has
        # no real data for yet. Trusting it would either wrongly mark the day
        # 'empty' or, worse, file another day's games under this one. Clear
        # the bad cache entry so the next run fetches for real instead of
        # replaying the same wrong page forever.
        cache_path.unlink(missing_ok=True)
        error = "schedule page didn't match the requested date -- likely a Baseball-Reference fallback page"
        logger.error("%s: %s (cache cleared, will retry on next run)", date_str, error)
        state_mod.set_day(state, date_str, season=season, extract_status="failed", extract_error=error, extract_checked_at=state_mod.now_iso())
        return

    # An empty postseason set is fine here: it only decides ref.is_postseason,
    # which this stage doesn't record. transform resolves the real tagging.
    refs = schedule.get_boxscore_refs(html, day, set())
    # A day's schedule page can occasionally echo a neighboring date's completed
    # games (e.g. a suspended game finished and posted under a later date) --
    # those refs embed their own (already-handled) date and get filed there
    # correctly by _download_game, but must not count toward *this* date's
    # completeness.
    own_date_refs = [r for r in refs if r.date == date_str]

    all_ok = True
    for ref in refs:
        if not _download_game(ref, session, state, redo, mode):
            all_ok = False

    if not own_date_refs:
        state_mod.set_day(state, date_str, season=season, extract_status="empty", game_count=0, extract_checked_at=state_mod.now_iso(), extract_error=None)
        logger.info("    %s: no games", date_str)
    else:
        state_mod.set_day(
            state, date_str, season=season, extract_status="done" if all_ok else "failed",
            game_count=len(own_date_refs), extract_checked_at=state_mod.now_iso(),
            extract_error=None if all_ok else "one or more games failed -- see games entries",
        )
        logger.info("    %s: %d game(s) %s", date_str, len(own_date_refs), "done" if all_ok else "completed with failures")

    logger.info("downloading %s complete", date_str)


def extract_range(start: datetime.date, end: datetime.date, force: bool = False, dry_run: bool = False) -> None:
    """--force means redo this stage's work: re-download pages already cached,
    for days already marked done. Both halves are the same idea -- this stage
    only downloads, so there is nothing else for the flag to mean.
    """
    mode = http_client.REFETCH if force else http_client.CACHE_FIRST

    state = state_mod.load()
    session = requests.Session()

    dates = list(_iter_dates(start, end))
    logger.info("extract: %s to %s (%d day(s) in season window)%s", start, end, len(dates), " [--force: re-downloading]" if force else "")

    for year in sorted({day.year for day in dates}):
        if dry_run:
            continue
        _download_season_schedule(year, session, mode)

    for day in dates:
        if dry_run:
            logger.info("[dry-run] would download %s", day.isoformat())
            continue
        _extract_day(day, session, state, force, mode)
