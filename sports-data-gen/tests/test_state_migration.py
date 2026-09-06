"""Migrating status.json from one `status` field to three.

A checkpoint in the pre-stages format carries one `status` per game, meaning
both "the HTML is cached" and "the JSON is written". Migration fans that onto
extract_status/transform_status, and every entry has to come across correctly
-- getting it wrong shows up as thousands of spuriously pending games, or
worse, as games silently considered done that aren't.

No fixtures, no network: each test writes a small status.json to tmp_path.
"""

from __future__ import annotations

import json

from mlb_scraper import state as state_mod

OLD_GAME = {
    "date": "2023-05-02",
    "season": 2023,
    "home_team": "CHN",
    "boxscore_url": "https://example.invalid/boxes/CHN/CHN202305020.shtml",
    "status": "done",
    "cache_path": "cache\\mlb\\2023\\2023-05-02\\CHN202305020.html",
    "hitting_json_path": "data\\mlb\\2023\\2023-05-02\\hitting\\hitting_CHN202305020.json",
    "pitching_json_path": "data\\mlb\\2023\\2023-05-02\\pitching\\pitching_CHN202305020.json",
    "scraped_at": "2023-05-03T02:17:21Z",
    "error": None,
    "attempts": 0,
    "upload_status": "done",
    "upload_error": None,
    "uploaded_at": "2023-05-03T03:00:00Z",
    "is_postseason": False,
}

OLD_DAY = {"season": 2023, "status": "done", "game_count": 14, "checked_at": "2023-05-03T02:17:50Z", "error": None}


def _write(tmp_path, days, games):
    path = tmp_path / "status.json"
    path.write_text(json.dumps({"days": days, "games": games}), encoding="utf-8")
    return path


def test_done_game_becomes_extracted_and_transformed(tmp_path):
    path = _write(tmp_path, {}, {"CHN202305020": dict(OLD_GAME)})

    entry = state_mod.load(path)["games"]["CHN202305020"]

    assert entry["extract_status"] == "done"
    assert entry["transform_status"] == "done"
    assert "status" not in entry, "the ambiguous field must not survive"
    # The pre-stages shape carries one timestamp, effectively the capture time.
    assert entry["extracted_at"] == OLD_GAME["scraped_at"]
    assert entry["transformed_at"] == OLD_GAME["scraped_at"]
    assert entry["extract_error"] is None
    # Everything the stages didn't own is carried across untouched.
    assert entry["upload_status"] == "done"
    assert entry["uploaded_at"] == OLD_GAME["uploaded_at"]
    assert entry["cache_path"] == OLD_GAME["cache_path"]
    assert entry["is_postseason"] is False


def test_failed_game_is_treated_as_an_extract_failure(tmp_path):
    """Which half failed isn't recoverable from the pre-stages shape, so it
    retries end to end rather than being assumed downloaded."""
    old = {**OLD_GAME, "status": "failed", "error": "404: ...", "attempts": 2}
    path = _write(tmp_path, {}, {"CHN202305020": old})

    entry = state_mod.load(path)["games"]["CHN202305020"]

    assert entry["extract_status"] == "failed"
    assert entry["extract_error"] == "404: ..."
    assert entry["attempts"] == 2
    assert entry.get("transform_status") is None, "a failed extract must not claim a transform"


def test_day_statuses_carry_across(tmp_path):
    path = _write(tmp_path, {"2023-05-02": dict(OLD_DAY), "2023-03-01": {**OLD_DAY, "status": "empty", "game_count": 0}}, {})

    days = state_mod.load(path)["days"]

    assert days["2023-05-02"]["extract_status"] == "done"
    assert days["2023-05-02"]["transform_status"] == "done"
    assert days["2023-05-02"]["extract_checked_at"] == OLD_DAY["checked_at"]
    assert days["2023-05-02"]["game_count"] == 14
    # 'empty' is a real outcome for both stages -- no games to download, none
    # to parse -- not a failure to carry forward.
    assert days["2023-03-01"]["extract_status"] == "empty"
    assert days["2023-03-01"]["transform_status"] == "empty"


def test_migration_is_idempotent_and_leaves_new_shape_alone(tmp_path):
    path = _write(tmp_path, {"2023-05-02": dict(OLD_DAY)}, {"CHN202305020": dict(OLD_GAME)})

    once = state_mod.load(path)
    state_mod.save(once, path)
    twice = state_mod.load(path)

    assert once == twice


def test_a_backup_is_written_before_the_old_shape_can_be_overwritten(tmp_path):
    path = _write(tmp_path, {}, {"CHN202305020": dict(OLD_GAME)})
    original = path.read_text(encoding="utf-8")

    state_mod.load(path)

    backup = path.with_suffix(path.suffix + state_mod.BACKUP_SUFFIX)
    assert backup.exists(), "migrating without a backup risks an unrecoverable checkpoint"
    assert backup.read_text(encoding="utf-8") == original


def test_an_already_migrated_file_gets_no_backup(tmp_path):
    """Nothing changed, so there is nothing to protect against."""
    path = _write(tmp_path, {}, {"CHN202305020": {"extract_status": "done", "transform_status": "done"}})

    state_mod.load(path)

    assert not path.with_suffix(path.suffix + state_mod.BACKUP_SUFFIX).exists()
