"""Console + file logging setup."""

from __future__ import annotations

import logging

import config


def setup_logging(verbose: bool = False) -> None:
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    # Overwritten (not appended) each run -- one run's log should never be
    # mixed up with another's. No rotation/history is kept; if a longer
    # backfill run's log is worth keeping, copy it out before the next run.
    file_handler = logging.FileHandler(config.LOG_DIR / "scraper.log", mode="w", encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
