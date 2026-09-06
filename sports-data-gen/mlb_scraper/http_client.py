"""The single chokepoint for every network request the scraper makes.

Caching is unconditional, not a mode: a cache hit means zero sleep and zero
network call. Completed box scores never change once posted, so there is no
reason to ever re-fetch a page that's already on disk -- fixing a parser bug
later just means re-running the same command, since every page is still
cached and only genuinely missing pages touch the network.
"""

from __future__ import annotations

import logging
import os
import random
import time
from pathlib import Path

import requests

import config

logger = logging.getLogger(__name__)


# How fetch() is allowed to get a page -- the two halves of `extract`, with
# and without --force. Reading from cache *without* downloading isn't a mode
# here: that's the transform stage, which never goes through this module at
# all. See cache.read().
CACHE_FIRST = "cache-first"  # read the cache, download only on a miss
REFETCH = "refetch"          # ignore the cache, always download


class FetchError(Exception):
    """Raised when a request exhausts its retries or gets an unexpected status."""


class NotFoundError(FetchError):
    """Raised immediately on a 404 -- non-transient, never retried."""


def _sleep_with_jitter() -> None:
    time.sleep(config.MIN_DELAY + random.uniform(0, config.JITTER_MAX))


def _backoff_sleep(attempt: int, retry_after: str | None = None) -> None:
    if retry_after is not None:
        try:
            delay = min(float(retry_after), config.BACKOFF_MAX)
        except ValueError:
            delay = config.BACKOFF_BASE**attempt
    else:
        delay = min(config.BACKOFF_BASE**attempt, config.BACKOFF_MAX)
    time.sleep(delay)


def _write_cache(cache_path: Path, text: str) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, cache_path)


def fetch(url: str, *, cache_path: Path, session: requests.Session, mode: str = CACHE_FIRST) -> str:
    """Returns the HTML for `url`, using the on-disk cache per `mode`.

    A cache hit skips rate limiting entirely -- no sleep, no request. A cache
    miss sleeps MIN_DELAY + jitter, then fetches with retry/backoff, writing
    the result to cache_path before returning it.

    REFETCH skips the cache-hit read (always fetches fresh) but still writes
    the result to cache_path afterward -- for pages that can change after being
    fetched once, like a season's still-in-progress schedule, where the usual
    "completed pages never change" caching assumption doesn't hold.
    """
    if mode != REFETCH and cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    # Checked here, past the cache read and before the sleep: a cache hit makes
    # no request and so needs no identity, nothing ever goes out over the wire
    # without one, and the failure lands immediately instead of MIN_DELAY late.
    if not config.USER_AGENT:
        raise config.ConfigError(
            "USER_AGENT is not set -- add it to .env (see .env.example). "
            "This scraper will not make a request without an identity you own."
        )

    _sleep_with_jitter()

    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            resp = session.get(
                url,
                headers={"User-Agent": config.USER_AGENT},
                timeout=config.REQUEST_TIMEOUT,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            logger.warning("request error (attempt %d/%d) for %s: %s", attempt, config.MAX_RETRIES, url, exc)
            if attempt == config.MAX_RETRIES:
                raise FetchError(f"network error after {config.MAX_RETRIES} attempts: {url}") from exc
            _backoff_sleep(attempt)
            continue

        if resp.status_code == 200:
            resp.encoding = resp.encoding or "utf-8"
            _write_cache(cache_path, resp.text)
            return resp.text

        if resp.status_code == 404:
            raise NotFoundError(f"404: {url}")

        if resp.status_code == 429 or 500 <= resp.status_code < 600:
            logger.warning(
                "status %d (attempt %d/%d) for %s", resp.status_code, attempt, config.MAX_RETRIES, url
            )
            if attempt == config.MAX_RETRIES:
                raise FetchError(f"status {resp.status_code} after {config.MAX_RETRIES} attempts: {url}")
            _backoff_sleep(attempt, resp.headers.get("Retry-After"))
            continue

        raise FetchError(f"unexpected status {resp.status_code}: {url}")

    raise FetchError(f"unreachable: {url}")
