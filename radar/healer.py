"""Auto-healing orchestration — the heart of the project.

When a run fails validation, we do not page a human. We:
  1. build a factual diagnosis from the validation report,
  2. hand it to `brightdata scraper heal <collector> "<diagnosis>"`,
  3. re-run the healed collector,
  4. re-validate, and record the whole intervention.

Scraper Studio does the actual repair; this module supplies the
detection, the diagnosis, and the retry loop around it.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from . import brightdata
from .config import HealthThresholds, Source
from .models import HealingEvent, ValidationReport
from .validator import build_heal_prompt, validate_run

logger = logging.getLogger(__name__)

RunFn = Callable[[str, str], list[dict[str, Any]]]
HealFn = Callable[..., str]


def attempt_heal(
    source: Source,
    failed_report: ValidationReport,
    thresholds: HealthThresholds,
    auto_approve: bool = True,
    run_fn: RunFn = brightdata.run_scraper,
    heal_fn: HealFn = brightdata.heal_scraper,
) -> tuple[HealingEvent, list[dict[str, Any]], ValidationReport]:
    """Heal a broken collector and re-run it.

    Returns (healing_event, rows_after, report_after). Never raises for
    CLI failures — a failed heal is recorded as outcome='failed' so the
    pipeline can continue with other sources.

    `run_fn`/`heal_fn` are injectable for tests and demos.
    """
    diagnosis = build_heal_prompt(failed_report, source.description)
    event = HealingEvent(
        source_id=source.id,
        collector_id=source.collector_id,
        diagnosis=failed_report.diagnosis(),
        rows_before=failed_report.rows_valid,
    )
    started = time.monotonic()
    logger.warning("Healing %s: %s", source.id, failed_report.diagnosis())

    try:
        heal_fn(
            source.collector_id, diagnosis, source.url, auto_approve=auto_approve
        )
        rows_after = run_fn(source.collector_id, source.url)
        report_after = validate_run(rows_after, thresholds)
        event.rows_after = report_after.rows_valid
        event.outcome = "healed" if report_after.healthy else "failed"
    except brightdata.BrightDataError as exc:
        logger.error("Heal of %s failed: %s", source.id, exc)
        rows_after, report_after = [], failed_report
        event.outcome = "failed"

    event.duration_seconds = time.monotonic() - started
    return event, rows_after, report_after
