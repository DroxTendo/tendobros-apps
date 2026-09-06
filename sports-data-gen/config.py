"""Project-wide constants for the MLB scraper."""

import os
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(Exception):
    """A required .env setting is missing. See .env.example."""


PROJECT_ROOT = Path(__file__).resolve().parent

# Loads .env (gitignored, real secrets) into the process environment if
# present; a no-op if it doesn't exist. USER_AGENT below is the one value a
# fresh clone must set before it can scrape; the cloud settings are only
# needed by `load`.
load_dotenv(PROJECT_ROOT / ".env")

# This app only scrapes MLB today, but the on-disk/cloud layout (SPORT/season/
# date/hitting|pitching) is deliberately sport-scoped, since NFL/NBA are
# planned to reuse the same storage/upload code later.
SPORT = "mlb"

BASE_URL = "https://www.baseball-reference.com"

# The exact User-Agent header every request is sent with. Operator-supplied and
# required: there is no default and no fallback, so nobody ever scrapes under
# someone else's identity. The whole string lives in .env (see .env.example) --
# name, version and contact are all yours. Keep it honest rather than
# impersonating a browser; that is the etiquette this project already follows
# everywhere else -- see the rate limiting below, and "Data source and terms"
# in README.md -- and it gives Baseball-Reference a way to identify and contact
# the client if they ever want to.
USER_AGENT = os.environ.get("USER_AGENT")

# Rate limiting: every real network request waits MIN_DELAY + random(0, JITTER_MAX) seconds.
MIN_DELAY = 5
JITTER_MAX = 2

MAX_RETRIES = 4
REQUEST_TIMEOUT = 15
BACKOFF_BASE = 2
BACKOFF_MAX = 30

# Regular-season games fall within this window for any given year; scraping
# outside it would just waste requests on guaranteed-empty schedule pages.
SEASON_START_MONTH_DAY = (3, 1)
SEASON_END_MONTH_DAY = (11, 30)

DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = PROJECT_ROOT / "cache"
STATE_PATH = PROJECT_ROOT / "state" / "status.json"
LOG_DIR = PROJECT_ROOT / "logs"

# Cloud upload settings, populated from .env (see .env.example) -- never
# hardcoded/committed. Only S3 is implemented today; AWS_REGION/S3_BUCKET
# being unset is fine unless `load` is actually invoked.
DEFAULT_UPLOAD_PROVIDER = os.environ.get("UPLOAD_PROVIDER", "s3")
AWS_REGION = os.environ.get("AWS_REGION")
S3_BUCKET = os.environ.get("S3_BUCKET")
