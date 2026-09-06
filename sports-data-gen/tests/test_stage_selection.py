"""Which games each stage picks up when no dates are given.

The point of tracking three statuses is that a game can sit between stages.
These pin the "catch up whatever is pending" behavior that makes a daily run
three bare commands with no date arithmetic.

No network, no fixtures.
"""

from __future__ import annotations

import datetime

import pytest

from mlb_scraper import state as state_mod
from mlb_scraper.stages import load as load_stage


def _game(date, **overrides):
    return {"date": date, "season": int(date[:4]), "transform_status": "done",
            "hitting_json_path": "h.json", "pitching_json_path": "p.json", **overrides}


STATE = {"days": {}, "games": {
    "PENDING": _game("2023-05-02"),                                   # transformed, not uploaded
    "UPLOADED": _game("2023-05-03", upload_status="done"),
    "NOT_TRANSFORMED": _game("2023-05-04", transform_status=None, extract_status="done"),
    "FAILED_UPLOAD": _game("2023-05-05", upload_status="failed"),     # retried
}}


@pytest.fixture
def captured(monkeypatch):
    """Run load_range as a dry run and collect which games it would upload."""
    monkeypatch.setattr(state_mod, "load", lambda: {"days": {}, "games": dict(STATE["games"])})
    monkeypatch.setattr(load_stage.state_mod, "load", lambda: {"days": {}, "games": dict(STATE["games"])})
    seen = []

    class _Log:
        def info(self, msg, *args):
            if "would upload" in msg:
                seen.append(args[0])

    monkeypatch.setattr(load_stage, "logger", _Log())
    return seen


def test_no_dates_uploads_everything_pending(captured):
    load_stage.load_range(dry_run=True)

    assert sorted(captured) == ["FAILED_UPLOAD", "PENDING"]
    assert "UPLOADED" not in captured, "an already-uploaded game must not be re-sent"
    assert "NOT_TRANSFORMED" not in captured, "a game with no JSON yet has nothing to upload"


def test_force_widens_to_everything_transformed(captured):
    load_stage.load_range(force=True, dry_run=True)

    assert sorted(captured) == ["FAILED_UPLOAD", "PENDING", "UPLOADED"]
    assert "NOT_TRANSFORMED" not in captured, "--force still can't upload a file that doesn't exist"


def test_dates_filter_independently(captured):
    load_stage.load_range(start=datetime.date(2023, 5, 5), dry_run=True)

    assert captured == ["FAILED_UPLOAD"]
