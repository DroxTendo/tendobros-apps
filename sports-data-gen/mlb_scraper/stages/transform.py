"""Stage 2: cache/ -> data/. Parses, and never opens a socket.

Everything this stage needs is already on disk, so it is free to re-run: a
parser fix is `transform --force` over the affected range, costing CPU and
nothing else.

Three things here are less obvious than they look:

* The day's schedule.html has to be re-parsed, not just the box scores.
  parse_boxscore matches HTML table ids against the *full* team names
  ("LosAngelesAngelsbatting"), and those names exist nowhere in status.json --
  only on the schedule page. It's one small page per ~15 box scores.
* is_postseason is resolved from the cached season_schedule.html. If that file
  is missing the season is skipped outright, because the alternative -- an
  empty postseason set -- would quietly rewrite every game that season as
  regular-season, replacing correct records with wrong ones.
* scraped_at is carried over from the extract stage, not stamped now.
  parse_boxscore stamps parse time, which is not the same as capture time:
  a 2023 page parsed today was still scraped in 2023, and the JSON should keep
  saying so.

Checkpointing is per day rather than per game. state.save() rewrites the whole
multi-MB file, and without a 5-7s network wait to hide behind, a full-corpus
run would spend most of its time writing status.json. A crash costs at most one
day of re-parsing, which is seconds.
"""

from __future__ import annotations

import datetime
import logging

from mlb_scraper import boxscore, cache, postseason, schedule, state as state_mod, storage

logger = logging.getLogger(__name__)


def _postseason_game_ids(year: int) -> set[str] | None:
    """None means "can't tag this season" -- the caller must skip it rather
    than treat it as "no postseason games"."""
    try:
        html = cache.read(cache.season_schedule_path(year))
    except cache.CacheMissError as exc:
        logger.error(
            "no cached season schedule for %d -- skipping the season rather than re-tagging every game "
            "as regular-season (run `extract` for a date in that season to fetch it): %s", year, exc,
        )
        return None
    return postseason.get_postseason_game_ids(html)


def _pending_days(state: dict, start: datetime.date | None, end: datetime.date | None, force: bool) -> list[str]:
    """Days whose HTML is cached and whose JSON is missing (or, under --force,
    whose JSON is to be rebuilt regardless)."""
    start_str = start.isoformat() if start else ""
    end_str = end.isoformat() if end else "9999-99-99"

    days = []
    for date_str, entry in state["days"].items():
        if entry.get("extract_status") not in ("done", "empty"):
            continue
        if not start_str <= date_str <= end_str:
            continue
        if not force and entry.get("transform_status") in ("done", "empty"):
            continue
        days.append(date_str)
    return sorted(days)


def _transform_game(ref, state, force: bool) -> bool:
    """Returns True if the game ended up transformed (either just now or
    already). Never raises for a missing page -- see the module docstring."""
    existing = state_mod.get_game(state, ref.game_id)
    if not force and existing and existing.get("transform_status") == "done":
        logger.info("    skipped already transformed: %s", ref.game_id)
        return True

    cache_path = cache.boxscore_path(ref.season, ref.date, ref.game_id)

    try:
        html = cache.read(cache_path)
    except cache.CacheMissError:
        # Not a failure of the game: whatever JSON an earlier run wrote is
        # still valid, so report its existing status rather than downgrading a
        # good 'done' entry over a page this stage simply doesn't have.
        logger.warning("    not cached, left as-is: %s", ref.game_id)
        return (existing or {}).get("transform_status") == "done"

    logger.info("    transforming game: %s", ref.game_id)
    try:
        record = boxscore.parse_boxscore(html, ref)
    except boxscore.ParseError as exc:
        logger.error("game %s failed to parse: %s", ref.game_id, exc)
        state_mod.update_game(state, ref.game_id, transform_status="failed", transform_error=str(exc))
        return False

    # parse_boxscore stamps *parse* time. The page was captured when extract
    # downloaded it, and re-parsing it later doesn't change when it was true.
    extracted_at = (existing or {}).get("extracted_at")
    if extracted_at:
        record.scraped_at = extracted_at

    hitting_path, pitching_path = storage.write_game_json(record)

    state_mod.update_game(
        state, ref.game_id,
        date=ref.date, season=ref.season, home_team=ref.home_code, boxscore_url=ref.url,
        is_postseason=ref.is_postseason,
        transform_status="done", transform_error=None, transformed_at=state_mod.now_iso(),
        hitting_json_path=state_mod.relpath(hitting_path),
        pitching_json_path=state_mod.relpath(pitching_path),
    )
    return True


def _transform_day(date_str: str, state, postseason_ids: set[str], force: bool) -> None:
    day = datetime.date.fromisoformat(date_str)
    season = day.year

    try:
        html = cache.read(cache.schedule_path(day))
    except cache.CacheMissError:
        logger.warning("%s: schedule not cached, left as-is", date_str)
        return

    logger.info("transforming %s", date_str)
    refs = schedule.get_boxscore_refs(html, day, postseason_ids)
    # As in extract: a schedule page can echo a neighboring date's completed
    # game, which files under its own date but must not count toward this
    # date's completeness.
    own_date_refs = [r for r in refs if r.date == date_str]

    all_ok = True
    for ref in refs:
        if not _transform_game(ref, state, force):
            all_ok = False

    if not own_date_refs:
        state_mod.update_day(state, date_str, season=season, transform_status="empty", transform_checked_at=state_mod.now_iso(), transform_error=None)
        logger.info("    %s: no games", date_str)
    else:
        state_mod.update_day(
            state, date_str, season=season, transform_status="done" if all_ok else "failed",
            transform_checked_at=state_mod.now_iso(),
            transform_error=None if all_ok else "one or more games failed -- see games entries",
        )
        logger.info("    %s: %d game(s) %s", date_str, len(own_date_refs), "done" if all_ok else "completed with failures")

    # One commit per day, not per game -- see the module docstring.
    state_mod.save(state)


def transform_range(start: datetime.date | None = None, end: datetime.date | None = None, force: bool = False, dry_run: bool = False) -> None:
    """With no dates, transforms everything extracted but not yet transformed.
    --force rebuilds the JSON for the whole range regardless of what's marked
    done.
    """
    state = state_mod.load()
    days = _pending_days(state, start, end, force)

    scope = f"{start or 'start'} to {end or 'end'}" if (start or end) else "all pending"
    logger.info("transform: %s -- %d day(s)%s", scope, len(days), " [--force: rebuilding]" if force else "")

    if not days:
        logger.info("nothing to transform")
        return

    postseason_by_season: dict[int, set[str] | None] = {}
    for date_str in days:
        year = int(date_str[:4])
        if year not in postseason_by_season:
            postseason_by_season[year] = None if dry_run else _postseason_game_ids(year)
            ids = postseason_by_season[year]
            if ids is not None:
                logger.info("%d: %d known postseason game(s)", year, len(ids))

        if dry_run:
            logger.info("[dry-run] would transform %s", date_str)
            continue

        if postseason_by_season[year] is None:
            continue  # season untaggable -- skip rather than mistag
        _transform_day(date_str, state, postseason_by_season[year], force)
