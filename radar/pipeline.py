"""Pipeline entrypoint: run every configured source once.

    python -m radar.pipeline                 # run all sources
    python -m radar.pipeline --source <id>   # run one source
    python -m radar.pipeline --simulate-breakage <id>
                                             # corrupt one source's rows in
                                             # memory to exercise the full
                                             # detect → heal → retry path

Run it on a schedule (cron, GitHub Actions) and the radar stays fresh
without any human attention — even when target sites change.
"""

from __future__ import annotations

import argparse
import logging
import sys

from . import brightdata
from .alerts import Notifier
from .config import Settings, Source, load_settings
from .healer import attempt_heal
from .models import RunRecord, rows_to_opportunities
from .store import Store
from .validator import validate_run

logger = logging.getLogger(__name__)


def process_source(
    source: Source,
    settings: Settings,
    store: Store,
    notifier: Notifier,
    simulate_breakage: bool = False,
) -> RunRecord:
    """Run one source end-to-end: scrape → validate → (heal) → store → alert."""
    record = RunRecord(source_id=source.id)

    if not source.is_configured:
        record.status, record.problems = "queued", (
            "no collector_id yet — run `brightdata scraper create` and update sources.yaml"
        )
        logger.warning("Skipping %s: %s", source.id, record.problems)
        return record

    try:
        rows = brightdata.run_scraper(source.collector_id, source.url)
    except brightdata.BrightDataError as exc:
        rows = []
        logger.error("Run failed for %s: %s", source.id, exc)

    if simulate_breakage:
        # Demo/chaos mode: emulate a site redesign by stripping the fields
        # the schema requires, so the detect → heal path fires for real.
        logger.warning("Simulating site breakage for %s", source.id)
        rows = [{k: v for k, v in row.items() if k not in ("title", "url", "link")}
                for row in rows]

    opportunities, row_errors = rows_to_opportunities(rows, source.id, source.category)
    report = validate_run(rows, settings.health, row_errors)

    if not report.healthy:
        event, rows, report = attempt_heal(
            source, report, settings.health, settings.auto_approve_heals
        )
        store.record_healing(event)
        notifier.notify_healing(event)
        opportunities, row_errors = rows_to_opportunities(
            rows, source.id, source.category
        )
        record.status = "healed" if event.outcome == "healed" else "failed"
    else:
        record.status = "ok"

    new_items = store.upsert_opportunities(opportunities) if report.healthy else []
    notifier.notify_new_opportunities(new_items)

    record.rows = report.rows_total
    record.new_rows = len(new_items)
    record.problems = report.diagnosis() if not report.healthy else ""
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Opportunity Radar pipeline.")
    parser.add_argument("--source", help="run only this source id")
    parser.add_argument(
        "--simulate-breakage",
        metavar="SOURCE_ID",
        help="corrupt this source's rows to demo the self-healing path",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    settings = load_settings()
    store = Store(settings.db_path)
    notifier = Notifier(settings.telegram_bot_token, settings.telegram_chat_id)

    exit_code = 0
    try:
        for source in settings.sources:
            if args.source and source.id != args.source:
                continue
            record = process_source(
                source, settings, store, notifier,
                simulate_breakage=(args.simulate_breakage == source.id),
            )
            store.record_run(record)
            logger.info(
                "%s: %s (%d rows, %d new)",
                source.id, record.status, record.rows, record.new_rows,
            )
            if record.status == "failed":
                exit_code = 1
    finally:
        store.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
