"""Golden-file regression tests for schedule.py.

2023-05-13 was chosen deliberately: it includes WAS202305130, a suspended
game that finished on a later date and gets a third `tr` (a "Completed on
M/D/YYYY" annotation row) inside `table.teams` -- the case that rejects the
whole game_summary block if that third row isn't tolerated. Locking in all 15
refs for this day catches a regression there, not just a narrow single-game
check.

2023-07-11 is the All-Star Game -- its game_summary block uses "National
League"/"American League" in place of a real team, which has no
`/teams/{CODE}/{YEAR}.shtml` link to resolve. It should produce zero refs
(not raise, not get mis-parsed as a franchise matchup) and log a warning
naming the unresolved team.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import logging
from pathlib import Path

from mlb_scraper import schedule
from tests.conftest import requires_fixture

FIXTURES = Path(__file__).parent / "fixtures"

pytestmark = requires_fixture(
    "schedule_2023-05-13.html", "schedule_2023-07-11.html"
)


def test_2023_05_13_matches_golden():
    html = (FIXTURES / "schedule_2023-05-13.html").read_text(encoding="utf-8")
    expected = json.loads((FIXTURES / "2023-05-13_refs_expected.json").read_text(encoding="utf-8"))

    refs = schedule.get_boxscore_refs(html, datetime.date(2023, 5, 13))
    actual = [dataclasses.asdict(r) for r in refs]

    assert actual == expected


def test_suspended_game_included():
    html = (FIXTURES / "schedule_2023-05-13.html").read_text(encoding="utf-8")
    refs = schedule.get_boxscore_refs(html, datetime.date(2023, 5, 13))
    game_ids = [r.game_id for r in refs]
    assert "WAS202305130" in game_ids


def test_all_star_game_produces_no_refs(caplog):
    html = (FIXTURES / "schedule_2023-07-11.html").read_text(encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="mlb_scraper.schedule"):
        refs = schedule.get_boxscore_refs(html, datetime.date(2023, 7, 11))

    assert refs == []
    assert any("National League" in message for message in caplog.messages)
