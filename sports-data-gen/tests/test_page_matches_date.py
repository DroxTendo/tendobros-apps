"""Regression test for schedule.page_matches_date.

The fallback page this guards against is real: Baseball-Reference returned it
for a 2026-08-07 request, and a "no games" result for that date turned out to
be a silently-served copy of 2026-08-06's page -- same 11 games, same boxscore
links. Its <title> has no "for {weekday}, {date}" clause, unlike a genuine
dated page; that's the signal this function checks for.

Both fixtures here are hand-written title-only stand-ins rather than captured
pages. page_matches_date() reads nothing but <title>, so they exercise it
exactly as the real pages did, they republish no Baseball-Reference content,
and they are committed -- which matters most for the fallback case, since
re-requesting 2026-08-07 today returns the genuine page and the original
anomaly can no longer be captured.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from mlb_scraper import schedule

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_genuine_dated_page_matches_its_own_date():
    html = _read("title_genuine_2023-05-13.html")
    assert schedule.page_matches_date(html, datetime.date(2023, 5, 13))


def test_genuine_dated_page_does_not_match_a_different_date():
    html = _read("title_genuine_2023-05-13.html")
    assert not schedule.page_matches_date(html, datetime.date(2023, 5, 14))


def test_fallback_page_never_matches_any_date():
    html = _read("title_fallback_dateless.html")
    assert not schedule.page_matches_date(html, datetime.date(2026, 8, 7))
    assert not schedule.page_matches_date(html, datetime.date(2026, 8, 6))
