"""Run-health validation — the pipeline's spider-sense.

A scraper rarely fails loudly when a site redesigns; it fails quietly,
returning empty arrays or rows full of nulls. This module turns those
quiet failures into a precise, machine-generated diagnosis that the
auto-healer can hand to `brightdata scraper heal`.
"""

from __future__ import annotations

from typing import Any

from .config import HealthThresholds
from .models import ValidationReport

# `brightdata scraper heal` rejects prompts over this length outright, so a
# verbose diagnosis silently costs us the repair we were trying to make.
MAX_HEAL_PROMPT_CHARS = 1000


def validate_run(
    rows: list[dict[str, Any]],
    thresholds: HealthThresholds,
    row_errors: list[str] | None = None,
) -> ValidationReport:
    """Judge a scraper run against schema and health thresholds."""
    problems: list[str] = []
    total = len(rows)

    if total == 0:
        return ValidationReport(
            healthy=False,
            rows_total=0,
            rows_valid=0,
            problems=["the scraper returned zero rows — extraction likely broken"],
        )

    if total < thresholds.min_rows:
        problems.append(
            f"only {total} rows returned (expected at least {thresholds.min_rows})"
        )

    for field in thresholds.required_fields:
        null_count = sum(1 for row in rows if not _has_value(row, field))
        ratio = null_count / total
        if ratio > thresholds.max_null_ratio:
            problems.append(
                f"required field '{field}' is missing or null in "
                f"{null_count}/{total} rows ({ratio:.0%})"
            )

    if row_errors:
        shown = "; ".join(row_errors[:3])
        problems.append(f"{len(row_errors)} rows failed schema validation ({shown})")

    valid = total - len(row_errors or [])
    return ValidationReport(
        healthy=not problems,
        rows_total=total,
        rows_valid=valid,
        problems=problems,
    )


def build_heal_prompt(report: ValidationReport, expected_schema: str) -> str:
    """Compose the natural-language repair prompt for Scraper Studio.

    Factual, specific, and states the expected output — exactly the
    kind of prompt `brightdata scraper heal` works best with.
    """
    head = "The scraper output failed validation: "
    tail = (
        f". The site layout may have changed. Expected output: {expected_schema}. "
        "Please repair the extraction so all expected fields are populated."
    )
    budget = MAX_HEAL_PROMPT_CHARS - len(head) - len(tail)
    diagnosis = report.diagnosis()
    if budget > 1 and len(diagnosis) > budget:
        diagnosis = diagnosis[: budget - 1] + "\u2026"
    return (head + diagnosis + tail)[:MAX_HEAL_PROMPT_CHARS]


def _has_value(row: dict[str, Any], field: str) -> bool:
    value = row.get(field)
    if value is None:
        # tolerate common aliases before declaring the field broken
        aliases = {"url": ("link", "href"), "title": ("name", "heading")}
        value = next(
            (row[a] for a in aliases.get(field, ()) if row.get(a) is not None), None
        )
    return value is not None and str(value).strip() != ""
