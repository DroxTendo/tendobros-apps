"""The transform stage's three non-obvious guarantees.

All three follow from parsing being a stage that can run long after the
download it depends on:

  * a re-parse must not restamp scraped_at with today's date;
  * a season whose schedule page isn't cached must be skipped, not re-tagged
    as if it had no postseason;
  * a missing cached page must leave existing records alone rather than
    marking anything failed.

Plus the per-day checkpointing that keeps a full-corpus run from spending its
life rewriting a multi-MB status.json.

No network, no fixtures.
"""

from __future__ import annotations

import datetime

import pytest

from mlb_scraper import cache, state as state_mod
from mlb_scraper.models import BoxscoreRef, GameRecord
from mlb_scraper.stages import transform

REF = BoxscoreRef(
    game_id="CHN202305020",
    date="2023-05-02",
    season=2023,
    game_seq=0,
    home_code="CHN",
    home_name="Chicago Cubs",
    away_code="LAD",
    away_name="Los Angeles Dodgers",
    url="https://example.invalid/boxes/CHN/CHN202305020.shtml",
)

EXTRACTED_AT = "2023-05-03T02:17:21Z"


@pytest.fixture
def cached_boxscore(monkeypatch, tmp_path):
    path = tmp_path / f"{REF.game_id}.html"
    path.write_text("<html>a box score</html>", encoding="utf-8")
    monkeypatch.setattr(cache, "boxscore_path", lambda season, date, game_id: path)
    return path


@pytest.fixture
def stub_parse(monkeypatch):
    """parse_boxscore stamps parse time -- that's the behavior under test."""

    def _parse(html, ref):
        return GameRecord(
            game_id=ref.game_id, date=ref.date, season=ref.season, game_seq=ref.game_seq,
            home_team=ref.home_code, away_team=ref.away_code, source_url=ref.url,
            scraped_at="2026-09-06T12:00:00Z",  # "now", long after the download
            is_postseason=ref.is_postseason, batting=[], pitching=[],
        )

    monkeypatch.setattr(transform.boxscore, "parse_boxscore", _parse)


def test_re_parse_keeps_the_original_capture_time(monkeypatch, cached_boxscore, stub_parse, tmp_path):
    """A 2023 page re-parsed in 2026 was still scraped in 2023. Without this,
    every transform --force would quietly relabel when the data was true."""
    written = {}

    def _capture(record):
        written["record"] = record
        return tmp_path / "h.json", tmp_path / "p.json"

    monkeypatch.setattr(transform.storage, "write_game_json", _capture)

    state = {"days": {}, "games": {REF.game_id: {"extract_status": "done", "extracted_at": EXTRACTED_AT}}}
    monkeypatch.setattr(state_mod, "relpath", lambda p: str(p))

    assert transform._transform_game(REF, state, force=True) is True
    assert written["record"].scraped_at == EXTRACTED_AT, "scraped_at drifted to parse time"
    # The transform's own timestamp is recorded separately, in state only.
    assert state["games"][REF.game_id]["transformed_at"] != EXTRACTED_AT


def test_a_missing_cached_page_leaves_a_done_record_alone(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "boxscore_path", lambda season, date, game_id: tmp_path / "absent.html")
    entry = {"extract_status": "done", "transform_status": "done", "transformed_at": EXTRACTED_AT}
    state = {"days": {}, "games": {REF.game_id: dict(entry)}}

    assert transform._transform_game(REF, state, force=True) is True
    assert state["games"][REF.game_id] == entry, "state was rewritten for a page we couldn't read"


def test_a_missing_cached_page_invents_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "boxscore_path", lambda season, date, game_id: tmp_path / "absent.html")
    state = {"days": {}, "games": {}}

    assert transform._transform_game(REF, state, force=True) is False
    assert state["games"] == {}


def test_a_season_without_a_cached_schedule_is_skipped_not_retagged(monkeypatch, tmp_path):
    """An empty postseason set would rewrite every game that season as
    regular-season. Returning None makes the caller skip instead."""
    monkeypatch.setattr(cache, "season_schedule_path", lambda year: tmp_path / "absent.html")

    assert transform._postseason_game_ids(2023) is None


def test_untaggable_seasons_transform_no_days(monkeypatch):
    monkeypatch.setattr(state_mod, "load", lambda: {
        "days": {"2023-05-02": {"extract_status": "done", "season": 2023}}, "games": {},
    })
    monkeypatch.setattr(transform, "_postseason_game_ids", lambda year: None)
    touched = []
    monkeypatch.setattr(transform, "_transform_day", lambda *a, **k: touched.append(a))

    transform.transform_range()

    assert touched == [], "days were transformed for a season that couldn't be tagged"


def test_checkpoint_is_per_day_not_per_game(monkeypatch):
    """state.save() rewrites the whole multi-MB file. With ~9,400 games and no
    network wait to hide behind, per-game commits would dominate the runtime."""
    saves = []
    monkeypatch.setattr(state_mod, "save", lambda state, *a, **k: saves.append(1))
    monkeypatch.setattr(transform.state_mod, "save", lambda state, *a, **k: saves.append(1))

    refs = [BoxscoreRef(**{**REF.__dict__, "game_id": f"GAME{n}"}) for n in range(5)]
    monkeypatch.setattr(transform.schedule, "get_boxscore_refs", lambda html, day, ids: refs)
    monkeypatch.setattr(cache, "read", lambda path: "<html></html>")
    monkeypatch.setattr(transform, "_transform_game", lambda ref, state, force: True)

    transform._transform_day("2023-05-02", {"days": {}, "games": {}}, set(), force=False)

    assert len(saves) == 1, f"expected one commit for the day, got {len(saves)} for 5 games"


def test_pending_days_selection():
    state = {"days": {
        "2023-05-01": {"extract_status": "done", "transform_status": "done"},
        "2023-05-02": {"extract_status": "done"},                      # pending
        "2023-05-03": {"extract_status": "failed"},                    # not extracted
        "2023-05-04": {"extract_status": "empty", "transform_status": "empty"},
    }, "games": {}}

    assert transform._pending_days(state, None, None, force=False) == ["2023-05-02"]
    # --force widens to everything extracted, transformed or not.
    assert transform._pending_days(state, None, None, force=True) == ["2023-05-01", "2023-05-02", "2023-05-04"]
    # Dates filter, and either bound may be omitted.
    assert transform._pending_days(state, datetime.date(2023, 5, 2), None, force=True) == ["2023-05-02", "2023-05-04"]
    assert transform._pending_days(state, None, datetime.date(2023, 5, 1), force=True) == ["2023-05-01"]
