"""Golden-file regression test for boxscore.py.

CHN202608050 (Cubs vs Dodgers, 2026-08-05) was manually reviewed and confirmed
correct, so its output is locked in as the known-good baseline -- these tests
only catch the parser drifting away from that baseline, they don't re-verify
the baseline itself is right.

Two things are deliberately not compared exactly:

- `scraped_at`, a fresh timestamp on every parse.
- The win-probability family (VOLATILE_STAT_DECIMALS below). Those are Baseball-
  Reference's own model outputs, not counted events, and they get recomputed
  upstream: re-fetching this page a year after it was captured returns the same
  35 players and the same counting stats, but ~20 of these values shifted by a
  unit or two in their last displayed decimal place. Comparing them exactly would mean the suite
  passes only against one particular capture of the page, which it can't, since
  the HTML fixtures are gitignored and rebuilt on demand (see
  tests/refresh_fixtures.py). They are still compared, within a tolerance, so a
  parser bug that mangles a column is still caught -- only upstream rounding
  drift is tolerated.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from mlb_scraper import boxscore
from mlb_scraper.models import BoxscoreRef
from tests.conftest import requires_fixture

FIXTURES = Path(__file__).parent / "fixtures"

pytestmark = requires_fixture("boxscore_CHN202608050.html")

# Win probability added, leverage index, championship WPA and run expectancy --
# derived from Baseball-Reference's models rather than counted from the game.
# The value is the number of decimal places the site displays that column to,
# which is what sets a meaningful tolerance: re24 drifting by 0.1 is one unit in
# its last place, exactly as wpa drifting by 0.001 is one in its own.
VOLATILE_STAT_DECIMALS = {
    "wpa_bat": 3, "wpa_bat_pos": 3, "wpa_bat_neg": 3, "wpa_def": 3,
    "re24_bat": 1, "re24_def": 1,
    "leverage_index_avg": 2, "cli_avg": 2,
    "cwpa_bat": 2, "cwpa_def": 2,
}

# Allow two units in the last displayed place. A full re-fetch a year on drifted
# by at most that; a parser reading the wrong column would miss by far more.
VOLATILE_ULPS = 2.5


def _tolerance(stat_name: str) -> float:
    return VOLATILE_ULPS * 10 ** -VOLATILE_STAT_DECIMALS[stat_name]


REF = BoxscoreRef(
    game_id="CHN202608050",
    date="2026-08-05",
    season=2026,
    game_seq=0,
    home_code="CHC",
    home_name="Chicago Cubs",
    away_code="LAD",
    away_name="Los Angeles Dodgers",
    url="https://www.baseball-reference.com/boxes/CHN/CHN202608050.shtml",
)


@pytest.fixture(scope="module")
def record():
    html = (FIXTURES / "boxscore_CHN202608050.html").read_text(encoding="utf-8")
    return boxscore.parse_boxscore(html, REF)


def _header(record) -> dict:
    return {
        "sport": "mlb",
        "game_id": record.game_id,
        "date": record.date,
        "season": record.season,
        "home_team": record.home_team,
        "away_team": record.away_team,
        "game_seq": record.game_seq,
        "source_url": record.source_url,
    }


def _load_expected(filename: str) -> dict:
    expected = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    expected.pop("scraped_at")
    return expected


def _as_number(value):
    """Percentage strings like "0.05%" come back as floats; anything else as-is."""
    if isinstance(value, str) and value.endswith("%"):
        try:
            return float(value[:-1])
        except ValueError:
            return value
    return value


def _split_volatile(players: list[dict]) -> tuple[list[dict], list[dict]]:
    """Separates each player's volatile stats from the rest, preserving order."""
    stable, volatile = [], []
    for player in players:
        stats = player.get("stats", {})
        stable.append({
            **{k: v for k, v in player.items() if k != "stats"},
            "stats": {k: v for k, v in stats.items() if k not in VOLATILE_STAT_DECIMALS},
        })
        volatile.append({k: _as_number(v) for k, v in stats.items() if k in VOLATILE_STAT_DECIMALS})
    return stable, volatile


def _assert_matches_golden(actual: dict, expected: dict, key: str) -> None:
    actual_stable, actual_volatile = _split_volatile(actual.pop(key))
    expected_stable, expected_volatile = _split_volatile(expected.pop(key))

    # Header fields, roster, ordering, and every counted stat: exact.
    assert {**actual, key: actual_stable} == {**expected, key: expected_stable}

    # Model-derived stats: present, numeric, and close.
    for actual_stats, expected_stats in zip(actual_volatile, expected_volatile):
        assert actual_stats.keys() == expected_stats.keys()
        for name, expected_value in expected_stats.items():
            assert actual_stats[name] == pytest.approx(expected_value, abs=_tolerance(name)), name


def test_hitting_matches_golden(record):
    expected = _load_expected("CHN202608050_hitting_expected.json")
    actual = {**_header(record), "batting": [asdict(b) for b in record.batting]}
    _assert_matches_golden(actual, expected, "batting")


def test_pitching_matches_golden(record):
    expected = _load_expected("CHN202608050_pitching_expected.json")
    actual = {**_header(record), "pitching": [asdict(p) for p in record.pitching]}
    _assert_matches_golden(actual, expected, "pitching")
