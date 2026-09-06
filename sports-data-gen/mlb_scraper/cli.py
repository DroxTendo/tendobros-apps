"""Argument parsing and command dispatch for `python -m mlb_scraper`.

See README.md for usage; run with --help for the full flag reference.
"""

from __future__ import annotations

import argparse
import datetime
import logging
from collections import Counter

import config
from mlb_scraper import cloud, state as state_mod
from mlb_scraper.logging_config import setup_logging
from mlb_scraper.stages import extract as extract_stage, load as load_stage, transform as transform_stage

logger = logging.getLogger(__name__)

# --start/--end are always required for extract, so this is purely a backstop:
# an explicit date more recent than (today in UTC) minus this many days gets
# capped, on the assumption it was a typo rather than a deliberate request to
# scrape games that may still be in progress. Hardcoded rather than a .env
# setting or a CLI flag, since lowering it would defeat the point. See
# _max_allowed_date() below for the UTC rationale. transform and load need no
# such cap -- neither can reach a game that extract never downloaded.
SAFE_LAG_DAYS = 1


def _max_allowed_date() -> datetime.date:
    """The latest date we'll ever scrape is (today in UTC) minus
    SAFE_LAG_DAYS. This deliberately uses UTC rather than a named
    timezone like America/New_York -- UTC needs no external tz database
    (datetime.timezone.utc is a fixed offset built into the stdlib), so this
    has zero dependencies and works identically anywhere the app runs.

    The tradeoff is that "today in UTC" isn't precisely "MLB's game day," so
    this relies on the app only being run once every game from the target
    dates is long over -- overnight or the next morning, never mid-slate.
    Run on that schedule, the one-day lag covers even West Coast games
    finishing well after Eastern midnight.
    """
    return datetime.datetime.now(datetime.timezone.utc).date() - datetime.timedelta(days=SAFE_LAG_DAYS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mlb_scraper")
    sub = parser.add_subparsers(dest="command", required=True)

    extract_p = sub.add_parser("extract", help="Download a date range from the web into cache/; a single day is --start == --end")
    extract_p.add_argument("--start", required=True, type=datetime.date.fromisoformat, help="YYYY-MM-DD (required)")
    extract_p.add_argument("--end", required=True, type=datetime.date.fromisoformat, help=f"YYYY-MM-DD (required); capped at {SAFE_LAG_DAYS} day(s) ago (UTC) -- recent dates may still have unfinished games, so they're never scraped. Only run this once all target dates' games are over (overnight/next-morning use is safe; running mid-slate is not)")
    extract_p.add_argument("--force", action="store_true", help="Re-download pages already cached. Slow by definition -- it re-pays MIN_DELAY for every page in the range")
    extract_p.add_argument("--dry-run", action="store_true", help="List dates that would be downloaded, without fetching")
    extract_p.add_argument("-v", "--verbose", action="store_true")

    transform_p = sub.add_parser("transform", help="Parse cached HTML into JSON under data/; with no dates, everything extracted but not yet transformed")
    transform_p.add_argument("--start", type=datetime.date.fromisoformat, help="YYYY-MM-DD; omit for no lower bound")
    transform_p.add_argument("--end", type=datetime.date.fromisoformat, help="YYYY-MM-DD; omit for no upper bound")
    transform_p.add_argument("--force", action="store_true", help="Rebuild JSON for games already transformed. Never touches the network, so this is what to run after a parser fix")
    transform_p.add_argument("--dry-run", action="store_true", help="List dates that would be transformed, without writing")
    transform_p.add_argument("-v", "--verbose", action="store_true")

    load_p = sub.add_parser("load", help="Upload transformed JSON to a cloud provider; with no dates, everything transformed but not yet uploaded")
    load_p.add_argument("--start", type=datetime.date.fromisoformat, help="YYYY-MM-DD; omit for no lower bound")
    load_p.add_argument("--end", type=datetime.date.fromisoformat, help="YYYY-MM-DD; omit for no upper bound")
    load_p.add_argument("--provider", choices=list(cloud.SUPPORTED_PROVIDERS), default=None, help=f"Defaults to UPLOAD_PROVIDER in .env, or {config.DEFAULT_UPLOAD_PROVIDER!r} if unset")
    load_p.add_argument("--force", action="store_true", help="Re-upload games already marked uploaded, overwriting those objects in the bucket")
    load_p.add_argument("--dry-run", action="store_true", help="List games that would be uploaded, without uploading")
    load_p.add_argument("-v", "--verbose", action="store_true")

    status_p = sub.add_parser("status", help="Show per-stage progress counts from status.json")
    status_p.add_argument("--season", type=int)

    return parser


def _counts(entries: list[dict], field: str) -> str:
    counts = Counter(e.get(field) for e in entries if e.get(field) is not None)
    return ", ".join(f"{status} {n}" for status, n in sorted(counts.items())) or "-"


def print_status(season: int | None = None) -> None:
    state = state_mod.load()
    days = list(state["days"].values())
    games = list(state["games"].values())

    if season is not None:
        days = [d for d in days if d.get("season") == season]
        games = [g for g in games if g.get("season") == season]

    print(f"Days ({len(days)} total)")
    print(f"  extract:   {_counts(days, 'extract_status')}")
    print(f"  transform: {_counts(days, 'transform_status')}")
    print(f"Games ({len(games)} total)")
    print(f"  extract:   {_counts(games, 'extract_status')}")
    print(f"  transform: {_counts(games, 'transform_status')}")
    print(f"  upload:    {_counts(games, 'upload_status')}")

    # What's stuck between stages -- the point of tracking each stage
    # separately.
    to_transform = sum(1 for g in games if g.get("extract_status") == "done" and g.get("transform_status") != "done")
    to_upload = sum(1 for g in games if g.get("transform_status") == "done" and g.get("upload_status") != "done")
    print(f"\nPending: {to_transform} to transform, {to_upload} to upload")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "extract":
        setup_logging(args.verbose)
        max_date = _max_allowed_date()
        start = args.start
        end = args.end
        if end < start:
            parser.error("--end must not be before --start")

        if start > max_date:
            logger.warning("--start %s is too recent; capping to %s (%d day(s) before today, UTC)", start, max_date, SAFE_LAG_DAYS)
            start = max_date
        if end > max_date:
            logger.warning("--end %s is too recent; capping to %s (%d day(s) before today, UTC)", end, max_date, SAFE_LAG_DAYS)
            end = max_date

        try:
            extract_stage.extract_range(start, end, force=args.force, dry_run=args.dry_run)
        except KeyboardInterrupt:
            logger.warning("interrupted -- state already saved, re-run the same command to resume")
            return 130
        except config.ConfigError as exc:
            parser.error(str(exc))
        return 0

    if args.command == "transform":
        setup_logging(args.verbose)
        if args.start and args.end and args.end < args.start:
            parser.error("--end must not be before --start")

        try:
            transform_stage.transform_range(args.start, args.end, force=args.force, dry_run=args.dry_run)
        except KeyboardInterrupt:
            logger.warning("interrupted -- completed days are recorded, re-run the same command to resume")
            return 130
        return 0

    if args.command == "load":
        setup_logging(args.verbose)
        if args.start and args.end and args.end < args.start:
            parser.error("--end must not be before --start")

        try:
            load_stage.load_range(args.start, args.end, provider=args.provider, force=args.force, dry_run=args.dry_run)
        except KeyboardInterrupt:
            logger.warning("interrupted -- already-uploaded games are recorded, re-run the same command to resume")
            return 130
        except (ValueError, NotImplementedError) as exc:
            parser.error(str(exc))
        return 0

    if args.command == "status":
        print_status(args.season)
        return 0

    parser.error("unknown command")
    return 2
