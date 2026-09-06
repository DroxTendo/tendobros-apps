"""Shared skip helper for tests that need real Baseball-Reference HTML.

The large HTML fixtures are gitignored (their terms of use restrict
redistribution), so a fresh clone has the golden JSON but not the pages that
produce it. Rather than failing with a bare FileNotFoundError, the tests that
need them skip with a message naming the script that fetches them back.

Tests that need no real page -- test_details_parser.py, and
test_page_matches_date.py via its two hand-written title_*.html stand-ins --
run on a fresh clone with no setup at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

_HINT = "run `python tests/refresh_fixtures.py` to fetch it (free if it's already in cache/)"


def requires_fixture(*names: str):
    """A skipif mark for tests needing gitignored fixture files."""
    missing = [name for name in names if not (FIXTURES / name).exists()]
    return pytest.mark.skipif(
        bool(missing),
        reason=f"missing fixture(s): {', '.join(missing)} -- {_HINT}",
    )
