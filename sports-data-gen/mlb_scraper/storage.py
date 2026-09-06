"""Writes a GameRecord out as two JSON files under
data/{sport}/{season}/{date}/hitting/hitting_{game_id}.json and
.../pitching/pitching_{game_id}.json. The hitting/pitching split is its own
subfolder (not just a filename prefix) so the same layout mirrors cleanly
into cloud storage; the filename keeps the hitting_/pitching_ prefix too,
purely for readability when browsing a folder directly. Both files carry the
same game-metadata header so each is self-contained -- independently
loadable/uploadable later without needing to open the other file just to
know what game it belongs to.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

import config
from mlb_scraper.models import GameRecord


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


def write_game_json(record: GameRecord, data_dir: Path = config.DATA_DIR) -> tuple[Path, Path]:
    day_dir = data_dir / config.SPORT / str(record.season) / record.date

    header = {
        # Always config.SPORT, not a GameRecord field -- the whole codebase
        # is single-sport-at-a-time today. When NFL/NBA are added, this is
        # where that sport's own value gets threaded through instead.
        "sport": config.SPORT,
        "game_id": record.game_id,
        "date": record.date,
        "season": record.season,
        "home_team": record.home_team,
        "away_team": record.away_team,
        "game_seq": record.game_seq,
        "source_url": record.source_url,
        "scraped_at": record.scraped_at,
        "is_postseason": record.is_postseason,
    }

    hitting_path = day_dir / "hitting" / f"hitting_{record.game_id}.json"
    pitching_path = day_dir / "pitching" / f"pitching_{record.game_id}.json"

    _atomic_write_json(hitting_path, {**header, "batting": [asdict(b) for b in record.batting]})
    _atomic_write_json(pitching_path, {**header, "pitching": [asdict(p) for p in record.pitching]})

    return hitting_path, pitching_path
