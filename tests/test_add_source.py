"""Tests for dashboard-added sources and local .env loading."""

import os
from pathlib import Path

import pytest
import yaml

from radar.config import _load_dotenv, append_extra_source, make_source_from_url


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


# -- .env loading -----------------------------------------------------

def test_dotenv_fills_missing_vars_but_never_overrides(tmp_path: Path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# comment line\n"
        "\n"
        "TELEGRAM_CHAT_ID=12345\n"
        'TELEGRAM_BOT_TOKEN="quoted-token"\n'
        "RADAR_AUTO_APPROVE=0\n"
    )
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("RADAR_AUTO_APPROVE", "1")  # real env must win

    _load_dotenv(env)

    assert os.environ["TELEGRAM_CHAT_ID"] == "12345"
    assert os.environ["TELEGRAM_BOT_TOKEN"] == "quoted-token"  # quotes stripped
    assert os.environ["RADAR_AUTO_APPROVE"] == "1"             # not overridden
