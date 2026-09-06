"""Repopulate the gitignored Baseball-Reference test fixtures.

The four large HTML fixtures aren't committed -- see README.md § Testing. This
rebuilds them, preferring the local cache/ tree (instant, no network) and
falling back to a real fetch through mlb_scraper.http_client, which applies the
project's usual MIN_DELAY + jitter rate limiting. Worst case that's four
requests and about half a minute.

Run from the project root:

    .venv\Scripts\python.exe tests/refresh_fixtures.py

The two title_*.html fixtures are committed and are never touched by this
script -- one of them stands in for a page that can no longer be re-fetched.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

import config
from mlb_scraper import http_client

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# (fixture filename, URL, path within cache/ that the scraper itself would use)
SOURCES = [
    (
        "boxscore_CHN202608050.html",
        f"{config.BASE_URL}/boxes/CHN/CHN202608050.shtml",
        "mlb/2026/2026-08-05/CHN202608050.html",
    ),
    (
        "schedule_2023-05-13.html",
        f"{config.BASE_URL}/boxes/index.fcgi?year=2023&month=5&day=13",
        "mlb/2023/2023-05-13/schedule.html",
    ),
    (
        "schedule_2023-07-11.html",
        f"{config.BASE_URL}/boxes/index.fcgi?year=2023&month=7&day=11",
        "mlb/2023/2023-07-11/schedule.html",
    ),
    (
        "season_schedule_2023.html",
        f"{config.BASE_URL}/leagues/majors/2023-schedule.shtml",
        "mlb/2023/season_schedule.html",
    ),
]


def main() -> int:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    fetched = 0

    for name, url, cache_rel in SOURCES:
        dest = FIXTURES / name
        if dest.exists():
            print(f"  ok       {name} (already present)")
            continue

        cached = config.CACHE_DIR / cache_rel
        if cached.exists():
            shutil.copyfile(cached, dest)
            print(f"  cache    {name} <- cache/{cache_rel}")
            continue

        print(f"  fetching {name} <- {url}")
        try:
            html = http_client.fetch(url, cache_path=cached, session=session)
        except http_client.FetchError as exc:
            print(f"  FAILED   {name}: {exc}", file=sys.stderr)
            return 1
        dest.write_text(html, encoding="utf-8")
        fetched += 1

    print(f"\nFixtures ready in {FIXTURES}" + (f" ({fetched} fetched)" if fetched else " (no network needed)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
