"""Regression test for postseason.py.

season_schedule_2023.html is the real, full `/leagues/majors/2023-schedule.shtml`
page -- it lists every 2023 game, regular season and postseason together, with
the postseason games grouped under their own explicit "Postseason Schedule"
heading. get_postseason_game_ids() should return exactly the game_ids listed
there, not the ~2,430 regular-season games on the rest of the page.
"""

from __future__ import annotations

from pathlib import Path

from mlb_scraper import postseason
from tests.conftest import requires_fixture

FIXTURES = Path(__file__).parent / "fixtures"


@requires_fixture("season_schedule_2023.html")
def test_postseason_game_ids_2023():
    html = (FIXTURES / "season_schedule_2023.html").read_text(encoding="utf-8")
    game_ids = postseason.get_postseason_game_ids(html)

    # Wild Card / Division Series openers from October 3, 2023.
    assert "MIL202310030" in game_ids
    assert "MIN202310030" in game_ids
    assert "PHI202310030" in game_ids
    assert "TBA202310030" in game_ids

    # A regular-season game (from the suspended-game fixture) must not be
    # swept in -- confirms parsing is scoped to the Postseason Schedule
    # section, not the whole page.
    assert "WAS202305130" not in game_ids


def test_no_postseason_section_returns_empty_set():
    assert postseason.get_postseason_game_ids("<html><body>nothing here</body></html>") == set()
