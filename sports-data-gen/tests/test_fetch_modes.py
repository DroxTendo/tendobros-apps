"""The two fetch modes, which are what `extract --force` actually means.

CACHE_FIRST (no flag) fills gaps; REFETCH (--force) never trusts the disk.
Reading from cache without ever downloading isn't a mode here -- that is the
transform stage, which doesn't go through http_client at all; see
tests/test_transform.py.

No network and no fixtures, so these run on a fresh clone.
"""

from __future__ import annotations

import pytest
import requests

import config
from mlb_scraper import http_client

CACHED = "<html>from the cache</html>"
DOWNLOADED = "<html>from the wire</html>"


@pytest.fixture
def forbid_network(monkeypatch):
    """Turn any request or rate-limit sleep into a test failure."""

    def _boom(*args, **kwargs):
        raise AssertionError("this mode must not touch the network")

    monkeypatch.setattr(http_client, "_sleep_with_jitter", _boom)
    monkeypatch.setattr(requests.Session, "get", _boom)


@pytest.fixture
def stub_network(monkeypatch):
    """Serve DOWNLOADED without sleeping, and count the requests."""
    calls = []

    class _Resp:
        status_code = 200
        encoding = "utf-8"
        text = DOWNLOADED
        headers: dict[str, str] = {}

    def _get(self, url, **kwargs):
        calls.append(url)
        return _Resp()

    monkeypatch.setattr(http_client, "_sleep_with_jitter", lambda: None)
    monkeypatch.setattr(requests.Session, "get", _get)
    monkeypatch.setattr(config, "USER_AGENT", "test-agent/1.0 (+https://example.invalid)")
    return calls


def _cached(tmp_path):
    path = tmp_path / "page.html"
    path.write_text(CACHED, encoding="utf-8")
    return path


def test_refetch_ignores_a_cached_page_and_overwrites_it(tmp_path, stub_network):
    cache_path = _cached(tmp_path)

    html = http_client.fetch(
        "https://example.invalid/page.html",
        cache_path=cache_path,
        session=requests.Session(),
        mode=http_client.REFETCH,
    )

    assert html == DOWNLOADED
    assert len(stub_network) == 1
    assert cache_path.read_text(encoding="utf-8") == DOWNLOADED


def test_cache_first_prefers_the_cache(tmp_path, forbid_network):
    assert http_client.fetch(
        "https://example.invalid/page.html",
        cache_path=_cached(tmp_path),
        session=requests.Session(),
    ) == CACHED


def test_cache_first_downloads_a_missing_page(tmp_path, stub_network):
    cache_path = tmp_path / "absent.html"

    html = http_client.fetch(
        "https://example.invalid/page.html",
        cache_path=cache_path,
        session=requests.Session(),
    )

    assert html == DOWNLOADED
    assert len(stub_network) == 1
    assert cache_path.read_text(encoding="utf-8") == DOWNLOADED
