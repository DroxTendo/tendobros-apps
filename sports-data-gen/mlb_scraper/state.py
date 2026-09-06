"""Checkpoint tracking via a single JSON file (state/status.json), not a database.

At this scale (a few thousand games across 4 seasons) a plain dict is simpler
than SQL/schema, and rewriting the whole file after each game is negligible
next to the 5-7s network wait it's paired with. Every write is atomic
(write to .tmp, then os.replace) so a crash mid-write can't corrupt it.

That "negligible" only holds for a stage that pairs each write with a network
call. `extract` does; `transform` doesn't, and re-parsing a day from cache is
cheap enough to redo -- so it batches via update_game/update_day and commits
once per day with an explicit save(). See stages/transform.py.

Each of the three stages owns its own status field (extract_status,
transform_status, upload_status) plus its own error/timestamp fields, so a
game can legitimately be extracted but not yet transformed. A checkpoint in
the older single-`status` format is migrated on load; see _migrate.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
from pathlib import Path

import config

_EMPTY_STATE: dict = {"days": {}, "games": {}}

# Written once, the first time a pre-stages status.json is read. The checkpoint
# is rebuildable from cache/ + data/ in principle, but not cheaply.
BACKUP_SUFFIX = ".pre-stages.bak"


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def relpath(path: Path) -> str:
    """Repo-relative form, which is how paths are recorded in status.json --
    an absolute path would be operator-specific and this repo is public."""
    return str(path.relative_to(config.PROJECT_ROOT))


def _migrate(data: dict) -> bool:
    """Fans a pre-stages `status` field out into per-stage fields.

    A checkpoint in the pre-stages format carries one `status` per entry,
    meaning both "the HTML is cached" and "the JSON is written". This maps
    that onto extract_status/transform_status.

    A 'failed' entry is the one genuinely lossy case: which of the two halves
    failed isn't recoverable from the file, so it's treated as an extract
    failure, which retries it end to end. Returns True if anything changed.
    """
    changed = False

    for entry in data.get("games", {}).values():
        if "extract_status" in entry:
            continue
        changed = True
        status = entry.pop("status", None)
        scraped_at = entry.pop("scraped_at", None)
        entry["extract_status"] = status
        entry["extracted_at"] = scraped_at
        entry["extract_error"] = entry.pop("error", None)
        if status == "done":
            entry["transform_status"] = "done"
            entry["transformed_at"] = scraped_at
            entry["transform_error"] = None

    for entry in data.get("days", {}).values():
        if "extract_status" in entry:
            continue
        changed = True
        status = entry.pop("status", None)
        checked_at = entry.pop("checked_at", None)
        entry["extract_status"] = status
        entry["extract_checked_at"] = checked_at
        entry["extract_error"] = entry.pop("error", None)
        if status in ("done", "empty"):
            entry["transform_status"] = status
            entry["transform_checked_at"] = checked_at
            entry["transform_error"] = None

    return changed


def load(path: Path = config.STATE_PATH) -> dict:
    if not path.exists():
        return {key: {} for key in _EMPTY_STATE}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    for key in _EMPTY_STATE:
        data.setdefault(key, {})

    if _migrate(data):
        # Before anything can be written back in the new shape, not after.
        backup = path.with_suffix(path.suffix + BACKUP_SUFFIX)
        if not backup.exists():
            shutil.copy2(path, backup)

    return data


def save(state: dict, path: Path = config.STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


def get_day(state: dict, date: str) -> dict | None:
    return state["days"].get(date)


def update_day(state: dict, date: str, **fields) -> None:
    """Merge fields without touching disk -- for stages that batch their
    checkpoint. set_day() is this plus an immediate save()."""
    state["days"][date] = {**state["days"].get(date, {}), **fields}


def set_day(state: dict, date: str, path: Path = config.STATE_PATH, **fields) -> None:
    update_day(state, date, **fields)
    save(state, path)


def get_game(state: dict, game_id: str) -> dict | None:
    return state["games"].get(game_id)


def update_game(state: dict, game_id: str, **fields) -> None:
    """Merge fields without touching disk. See update_day."""
    state["games"][game_id] = {**state["games"].get(game_id, {}), **fields}


def set_game(state: dict, game_id: str, path: Path = config.STATE_PATH, **fields) -> None:
    update_game(state, game_id, **fields)
    save(state, path)
