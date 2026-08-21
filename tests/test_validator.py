"""Tests for run-health validation and heal-prompt generation."""

from radar.config import HealthThresholds
from radar.validator import build_heal_prompt, validate_run

THRESHOLDS = HealthThresholds(min_rows=3, max_null_ratio=0.4, required_fields=("title", "url"))


def _rows(n: int, **overrides):
    return [
        {"title": f"Opportunity {i}", "url": f"https://example.org/{i}", **overrides}
        for i in range(n)
    ]


def test_healthy_run_passes():
    report = validate_run(_rows(5), THRESHOLDS)
    assert report.healthy
    assert report.rows_total == 5
    assert report.problems == []


def test_zero_rows_is_unhealthy():
    report = validate_run([], THRESHOLDS)
    assert not report.healthy
    assert "zero rows" in report.diagnosis()


def test_too_few_rows_is_unhealthy():
    report = validate_run(_rows(2), THRESHOLDS)
    assert not report.healthy
    assert "only 2 rows" in report.diagnosis()


def test_null_required_field_is_unhealthy():
    rows = _rows(10)
    for row in rows[:6]:  # 60% nulls > 40% threshold
        row["title"] = None
    report = validate_run(rows, THRESHOLDS)
    assert not report.healthy
    assert "'title'" in report.diagnosis()


def test_null_ratio_below_threshold_is_tolerated():
    rows = _rows(10)
    rows[0]["title"] = None  # 10% nulls < 40% threshold
    report = validate_run(rows, THRESHOLDS)
    assert report.healthy


def test_url_aliases_count_as_present():
    rows = [{"title": f"T{i}", "link": f"https://example.org/{i}"} for i in range(5)]
    report = validate_run(rows, THRESHOLDS)
    assert report.healthy


def test_heal_prompt_contains_diagnosis_and_schema():
    report = validate_run([], THRESHOLDS)
    prompt = build_heal_prompt(report, "titles and urls of scholarships")
    assert "zero rows" in prompt
    assert "titles and urls of scholarships" in prompt
