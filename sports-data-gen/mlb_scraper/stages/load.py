"""Stage 3: data/ -> cloud storage. Uploads, and nothing else.

Only games the transform stage has finished are candidates -- this never
touches the source site, and never looks at cache/. --force re-uploads games
already marked uploaded, which is an unguarded overwrite of those objects.
"""

from __future__ import annotations

import datetime
import logging
from itertools import groupby

import config
from mlb_scraper import cloud, state as state_mod

logger = logging.getLogger(__name__)


def _remote_key(relpath: str) -> str:
    """Mirrors the on-disk data/{sport}/{season}/{date}/hitting|pitching/...
    layout into the cloud 1:1, dropping only the leading 'data/' -- that's a
    local storage detail, not something a bucket key should carry -- so a
    key looks like mlb/2026/2026-08-04/hitting/hitting_BAL202608040.json.
    """
    posix = relpath.replace("\\", "/")
    data_root = config.DATA_DIR.name + "/"
    if posix.startswith(data_root):
        posix = posix[len(data_root):]
    return posix


def _process_game_upload(game_id: str, entry: dict, uploader, state) -> bool:
    hitting_rel = entry["hitting_json_path"]
    pitching_rel = entry["pitching_json_path"]

    try:
        uploader.upload_file(config.PROJECT_ROOT / hitting_rel, _remote_key(hitting_rel))
        uploader.upload_file(config.PROJECT_ROOT / pitching_rel, _remote_key(pitching_rel))
    except Exception as exc:  # boto3 raises its own ClientError hierarchy -- catch broadly, log, keep going
        logger.error("upload failed for game %s: %s", game_id, exc)
        state_mod.set_game(state, game_id, upload_status="failed", upload_error=str(exc))
        return False

    state_mod.set_game(state, game_id, upload_status="done", uploaded_at=state_mod.now_iso(), upload_error=None)
    return True


def load_range(start: datetime.date | None = None, end: datetime.date | None = None, provider: str | None = None, force: bool = False, dry_run: bool = False) -> None:
    """Uploads the hitting/pitching JSON for every transformed game in range;
    with no dates, for everything transformed but not yet uploaded.

    Independent of extract's season-window/date-capping rules -- this only
    ever looks at games already recorded in status.json, so an out-of-season
    or future date range simply finds nothing to upload rather than erroring.
    """
    provider = provider or config.DEFAULT_UPLOAD_PROVIDER
    state = state_mod.load()
    start_str = start.isoformat() if start else ""
    end_str = end.isoformat() if end else "9999-99-99"

    games = {
        gid: entry for gid, entry in state["games"].items()
        if entry.get("transform_status") == "done" and start_str <= entry.get("date", "") <= end_str
    }
    scope = f"{start or 'start'} to {end or 'end'}" if (start or end) else "all pending"
    logger.info("load: %s via %s -- %d transformed game(s) in range", scope, provider, len(games))

    all_games = sorted(games.items(), key=lambda item: (item[1].get("date", ""), item[0]))

    def _needs_upload(entry: dict) -> bool:
        return force or entry.get("upload_status") != "done"

    total = len(all_games)
    to_upload = sum(1 for _, entry in all_games if _needs_upload(entry))
    already_done = total - to_upload

    if dry_run:
        for gid, entry in all_games:
            if _needs_upload(entry):
                logger.info("[dry-run] would upload %s", gid)
            else:
                logger.info("[dry-run] skipped already uploaded: %s", gid)
        logger.info("[dry-run] %d to upload, %d already uploaded", to_upload, already_done)
        return

    # Only construct a real cloud client when there's at least one game that
    # actually needs it -- a date with nothing to upload collapses to a
    # single log line below and never touches the uploader.
    uploader = None
    ok = fail = 0
    processed = 0
    for date_key, group_iter in groupby(all_games, key=lambda item: item[1].get("date", "")):
        group = list(group_iter)

        if not any(_needs_upload(entry) for _, entry in group):
            processed += len(group)
            logger.info("skipping %s, all games uploaded", date_key)
            continue

        logger.info("uploading %s...", date_key)
        for gid, entry in group:
            if not _needs_upload(entry):
                logger.info("    skipped already uploaded: %s", gid)
            else:
                if uploader is None:
                    uploader = cloud.get_uploader(provider)
                logger.info("    uploading game: %s", gid)
                if _process_game_upload(gid, entry, uploader, state):
                    ok += 1
                else:
                    fail += 1
            processed += 1
        logger.info("uploading %s... complete, %d/%d overall complete", date_key, processed, total)

    logger.info("upload complete: %d uploaded, %d already done, %d failed", ok, already_done, fail)
