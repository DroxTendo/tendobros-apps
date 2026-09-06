import pytest

from mlb_scraper.details_parser import parse_details


@pytest.mark.parametrize("raw", ["", None])
def test_empty_input(raw):
    stats, unrecognized = parse_details(raw)
    assert unrecognized == []
    assert all(v == 0 for v in stats.values())


def test_plain_code():
    stats, unrecognized = parse_details("HR")
    assert stats["HR"] == 1
    assert unrecognized == []


def test_counted_code():
    stats, unrecognized = parse_details("2·2B")
    assert stats["2B"] == 2
    assert unrecognized == []


def test_multiple_tokens():
    stats, unrecognized = parse_details("2·2B,SF,GDP")
    assert stats["2B"] == 2
    assert stats["SF"] == 1
    assert stats["GDP"] == 1
    assert stats["HR"] == 0
    assert unrecognized == []


def test_bogus_token():
    stats, unrecognized = parse_details("HR,#wat")
    assert stats["HR"] == 1
    assert unrecognized == ["#wat"]


def test_intentional_walk_alias():
    stats, unrecognized = parse_details("IW")
    assert stats["IBB"] == 1
    assert unrecognized == []
