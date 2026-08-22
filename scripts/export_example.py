"""Regenerate data/example_output.json from the radar database.

Usage: python scripts/export_example.py [source_id]
Run the pipeline first so the store holds real rows.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from radar.config import load_settings  # noqa: E402
from radar.store import Store  # noqa: E402


def main() -> None:
    source_id = sys.argv[1] if len(sys.argv) > 1 else None
    store = Store(load_settings().db_path)
    try:
        items = store.list_opportunities()
    finally:
        store.close()
    if source_id:
        items = [item for item in items if item["source_id"] == source_id]
    if not items:
        sys.exit("no rows in the store — run `python -m radar.pipeline` first")

    out = {
        "_comment": (
            "Real structured output produced by the pipeline. Dates without a "
            "year in the source are inferred (rolled forward when past). "
            "Regenerate with: python scripts/export_example.py"
        ),
        "source_id": source_id or "all",
        "rows": [
            {k: v for k, v in item.items() if k not in ("fingerprint", "first_seen", "last_seen")}
            for item in items[:8]
        ],
    }
    path = Path(__file__).resolve().parent.parent / "data" / "example_output.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {path} with {len(out['rows'])} rows")


if __name__ == "__main__":
    main()
