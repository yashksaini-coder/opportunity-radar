"""Tests for input validation and API hardening."""

import time

import pytest

from dashboard.security import SlidingWindowLimiter
from radar.config import Source, _validate_sources
from radar.models import Opportunity, rows_to_opportunities


def _source(**overrides) -> Source:
    base = dict(
        id="demo-source", name="Demo", url="https://example.org/list",
        collector_id="c_abc123", category="hackathon", description="stuff",
    )
    base.update(overrides)
    return Source(**base)


# -- source validation ------------------------------------------------

def test_valid_source_passes():
    _validate_sources((_source(),))


def test_government_domain_is_rejected():
    with pytest.raises(ValueError, match="government"):
        _validate_sources((_source(url="https://grants.gov/listing"),))


def test_non_http_url_is_rejected():
    with pytest.raises(ValueError, match="http"):
        _validate_sources((_source(url="ftp://example.org/x"),))


def test_duplicate_ids_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        _validate_sources((_source(), _source()))


def test_bad_collector_id_is_rejected():
    with pytest.raises(ValueError, match="collector_id"):
        _validate_sources((_source(collector_id="rm -rf /"),))


def test_bad_source_id_is_rejected():
    with pytest.raises(ValueError, match="source id"):
        _validate_sources((_source(id="Bad Id!"),))


# -- scraped-data validation ------------------------------------------

def test_javascript_url_is_rejected():
    with pytest.raises(ValueError):
        Opportunity(title="x", url="javascript:alert(1)", category="other", source_id="s")


def test_rows_with_unsafe_urls_are_dropped_and_reported():
    rows = [
        {"title": "Good", "url": "https://example.org/a"},
        {"title": "Evil", "url": "javascript:alert(1)"},
    ]
    valid, errors = rows_to_opportunities(rows, "s", "other")
    assert len(valid) == 1
    assert len(errors) == 1


def test_overlong_title_is_capped():
    opp = Opportunity(title="x" * 1000, url="https://e.org", category="other", source_id="s")
    assert len(opp.title) == 300


# -- rate limiter -----------------------------------------------------

def test_limiter_allows_within_budget():
    limiter = SlidingWindowLimiter({"api": (5, 60)})
    now = time.monotonic()
    assert all(limiter.check("1.2.3.4", "api", now) == 0.0 for _ in range(5))


def test_limiter_blocks_over_budget_and_isolates_clients():
    limiter = SlidingWindowLimiter({"api": (3, 60)})
    now = time.monotonic()
    for _ in range(3):
        assert limiter.check("attacker", "api", now) == 0.0
    assert limiter.check("attacker", "api", now) > 0       # blocked
    assert limiter.check("innocent", "api", now) == 0.0    # unaffected


def test_limiter_window_slides():
    limiter = SlidingWindowLimiter({"api": (2, 10)})
    now = time.monotonic()
    assert limiter.check("c", "api", now) == 0.0
    assert limiter.check("c", "api", now) == 0.0
    assert limiter.check("c", "api", now) > 0
    assert limiter.check("c", "api", now + 11) == 0.0  # window expired
