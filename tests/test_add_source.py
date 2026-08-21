"""Tests for dashboard-added sources (make_source_from_url + persistence)."""

from pathlib import Path

import pytest
import yaml

from radar.config import append_extra_source, make_source_from_url


def test_builds_valid_source_from_url():
    src = make_source_from_url("https://www.buddy4study.com/scholarships", set())
    assert src.id == "buddy4study"
    assert src.url == "https://www.buddy4study.com/scholarships"
    assert not src.is_configured  # queued until a collector exists


def test_slug_dedupes_against_existing_ids():
    src = make_source_from_url("https://buddy4study.com/x", {"buddy4study", "buddy4study-2"})
    assert src.id == "buddy4study-3"


def test_rejects_bare_or_non_http_input():
    with pytest.raises(ValueError):
        make_source_from_url("buddy4study.com", set())
    with pytest.raises(ValueError):
        make_source_from_url("ftp://example.org/x", set())


def test_rejects_government_domain():
    with pytest.raises(ValueError, match="government"):
        make_source_from_url("https://scholarships.gov.in/list", set())


def test_append_extra_source_round_trips(tmp_path: Path):
    extra = tmp_path / "sources.extra.yaml"
    first = make_source_from_url("https://example.org/a", set())
    second = make_source_from_url("https://another.org/b", {first.id})
    append_extra_source(first, extra)
    append_extra_source(second, extra)

    data = yaml.safe_load(extra.read_text())
    ids = [entry["id"] for entry in data["sources"]]
    assert ids == [first.id, second.id]
    assert data["sources"][0]["collector_id"] == ""
