"""Tests for the SQLite store: dedupe, run log, healing log."""

from pathlib import Path

import pytest

from radar.models import HealingEvent, Opportunity, RunRecord
from radar.store import Store


@pytest.fixture()
def store(tmp_path: Path):
    s = Store(tmp_path / "test.db")
    yield s
    s.close()


def _opp(title: str = "Hack the Web", url: str = "https://example.org/h") -> Opportunity:
    return Opportunity(title=title, url=url, category="hackathon", source_id="test")


def test_upsert_returns_only_new(store: Store):
    first = store.upsert_opportunities([_opp(), _opp("Other", "https://example.org/o")])
    assert len(first) == 2

    second = store.upsert_opportunities([_opp()])  # duplicate
    assert second == []
    assert len(store.list_opportunities()) == 2


def test_category_filter(store: Store):
    store.upsert_opportunities([_opp()])
    assert store.list_opportunities("hackathon")
    assert store.list_opportunities("scholarship") == []


def test_run_and_healing_logs_round_trip(store: Store):
    store.record_run(RunRecord(source_id="test", status="healed", rows=9, new_rows=4))
    store.record_healing(
        HealingEvent(
            source_id="test", collector_id="c_abc", diagnosis="zero rows",
            outcome="healed", rows_before=0, rows_after=9, duration_seconds=42.0,
        )
    )
    runs = store.recent_runs()
    heals = store.healing_log()
    assert runs[0]["status"] == "healed"
    assert heals[0]["outcome"] == "healed"
    assert heals[0]["rows_after"] == 9
