"""The user-agent guard in http_client.fetch().

USER_AGENT is operator-supplied and has no default, so the scraper must refuse
to make a request without one -- that is the whole point of moving it into
.env. Two properties are worth pinning, because both are easy to break by
moving the check a few lines:

  * a cache miss raises before sleeping, so nothing goes out unidentified and
    the failure is immediate rather than MIN_DELAY seconds late; and
  * a cache *hit* still works unconfigured, so re-parsing already-scraped
    pages from cache/ after a parser fix keeps costing no network and no
    configuration.

Neither test touches the network or needs a fixture, so both run on a fresh
clone.
"""

from __future__ import annotations

import pytest
import requests

import config
from mlb_scraper import http_client


@pytest.fixture
def no_user_agent(monkeypatch):
    monkeypatch.setattr(config, "USER_AGENT", None)


@pytest.fixture
def forbid_network(monkeypatch):
    """Turn any request or rate-limit sleep into a test failure."""

    def _boom(*args, **kwargs):
        raise AssertionError("fetch() should not have got this far")

    monkeypatch.setattr(http_client, "_sleep_with_jitter", _boom)
    monkeypatch.setattr(requests.Session, "get", _boom)


def test_cache_miss_without_user_agent_raises_before_sleeping(tmp_path, no_user_agent, forbid_network):
    with pytest.raises(config.ConfigError) as excinfo:
        http_client.fetch(
            "https://example.invalid/page.html",
            cache_path=tmp_path / "missing.html",
            session=requests.Session(),
        )

    # The message has to name the variable and the file to set it in.
    assert "USER_AGENT" in str(excinfo.value)
    assert ".env" in str(excinfo.value)


def test_empty_user_agent_is_treated_as_unset(tmp_path, monkeypatch, forbid_network):
    monkeypatch.setattr(config, "USER_AGENT", "")

    with pytest.raises(config.ConfigError):
        http_client.fetch(
            "https://example.invalid/page.html",
            cache_path=tmp_path / "missing.html",
            session=requests.Session(),
        )


def test_cache_hit_still_works_without_user_agent(tmp_path, no_user_agent, forbid_network):
    cache_path = tmp_path / "cached.html"
    cache_path.write_text("<html>cached</html>", encoding="utf-8")

    html = http_client.fetch(
        "https://example.invalid/page.html",
        cache_path=cache_path,
        session=requests.Session(),
    )

    assert html == "<html>cached</html>"


def test_bypass_cache_still_requires_a_user_agent(tmp_path, no_user_agent, forbid_network):
    """The season-schedule page skips the cache read, so it goes to the network
    even when a copy exists -- and must be identified like any other request."""
    cache_path = tmp_path / "cached.html"
    cache_path.write_text("<html>cached</html>", encoding="utf-8")

    with pytest.raises(config.ConfigError):
        http_client.fetch(
            "https://example.invalid/page.html",
            cache_path=cache_path,
            session=requests.Session(),
            mode=http_client.REFETCH,
        )
