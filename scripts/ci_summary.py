"""Emit a Markdown summary of the latest pipeline run for CI.

Used by .github/workflows/scrape.yml to write the job summary:
per-source status, row counts, and any self-healing interventions.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar.config import load_settings  # noqa: E402
from radar.store import Store  # noqa: E402

STATUS_EMOJI = {"ok": "🟢", "healed": "🔧", "failed": "🔴", "queued": "⏳"}


def main() -> None:
    settings = load_settings()
    store = Store(settings.db_path)
    try:
        runs = store.recent_runs(limit=50)
        heals = store.healing_log(limit=10)
        opportunities = store.list_opportunities()
    finally:
        store.close()

    latest: dict[str, dict] = {}
    for run in runs:
        latest.setdefault(run["source_id"], run)

    print("## 🕸️ Opportunity Radar — nightly run")
    print()
    print(f"**{len(opportunities)} opportunities tracked** across "
          f"{len(latest)} sources.")
    print()
    print("| Source | Status | Rows | New |")
    print("|---|---|---:|---:|")
    for source_id, run in latest.items():
        emoji = STATUS_EMOJI.get(run["status"], "❓")
        print(f"| `{source_id}` | {emoji} {run['status']} "
              f"| {run['rows']} | {run['new_rows']} |")

    if heals:
        print()
        print("### 🕷️ Spider-sense log (recent self-heals)")
        print()
        for event in heals[:5]:
            print(f"- **{event['source_id']}** at {event['triggered_at'][:16]} — "
                  f"“{event['diagnosis']}” → **{event['outcome']}** "
                  f"({event['rows_before']}→{event['rows_after']} rows, "
                  f"{event['duration_seconds']:.0f}s)")
    else:
        print()
        print("_No healing needed — the web was calm tonight._")


if __name__ == "__main__":
    main()
