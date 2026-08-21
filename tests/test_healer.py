"""Tests for the auto-heal orchestration, with the CLI faked out."""

from radar.config import HealthThresholds, Source
from radar.healer import attempt_heal
from radar.validator import validate_run

THRESHOLDS = HealthThresholds(min_rows=3, max_null_ratio=0.4, required_fields=("title", "url"))

SOURCE = Source(
    id="demo", name="Demo", url="https://example.org",
    collector_id="c_demo123", category="hackathon",
    description="titles and urls of hackathons",
)

GOOD_ROWS = [
    {"title": f"Hackathon {i}", "url": f"https://example.org/{i}"} for i in range(5)
]


def test_successful_heal_records_event_and_rows():
    failed = validate_run([], THRESHOLDS)
    heal_calls: list[str] = []

    event, rows, report = attempt_heal(
        SOURCE, failed, THRESHOLDS,
        run_fn=lambda cid, url: GOOD_ROWS,
        heal_fn=lambda cid, diagnosis, url, auto_approve: heal_calls.append(diagnosis) or "ok",
    )

    assert event.outcome == "healed"
    assert report.healthy
    assert len(rows) == 5
    assert heal_calls and "zero rows" in heal_calls[0]
    assert "titles and urls of hackathons" in heal_calls[0]


def test_failed_heal_is_recorded_not_raised():
    from radar.brightdata import BrightDataError

    failed = validate_run([], THRESHOLDS)

    def broken_heal(*args, **kwargs):
        raise BrightDataError("heal exploded")

    event, rows, report = attempt_heal(
        SOURCE, failed, THRESHOLDS,
        run_fn=lambda cid, url: GOOD_ROWS,
        heal_fn=broken_heal,
    )

    assert event.outcome == "failed"
    assert rows == []
    assert not report.healthy


def test_heal_that_does_not_fix_output_is_marked_failed():
    failed = validate_run([], THRESHOLDS)

    event, rows, report = attempt_heal(
        SOURCE, failed, THRESHOLDS,
        run_fn=lambda cid, url: [],           # still broken after "healing"
        heal_fn=lambda *a, **k: "ok",
    )

    assert event.outcome == "failed"
    assert not report.healthy
