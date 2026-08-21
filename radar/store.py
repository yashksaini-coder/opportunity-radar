"""SQLite persistence: opportunities, run history, healing events."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import HealingEvent, Opportunity, RunRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities (
    fingerprint TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    organization TEXT,
    deadline TEXT,
    amount TEXT,
    location TEXT,
    category TEXT NOT NULL,
    source_id TEXT NOT NULL,
    tags TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    status TEXT NOT NULL,
    rows INTEGER NOT NULL,
    new_rows INTEGER NOT NULL,
    problems TEXT
);
CREATE TABLE IF NOT EXISTS healing_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    collector_id TEXT NOT NULL,
    triggered_at TEXT NOT NULL,
    diagnosis TEXT NOT NULL,
    outcome TEXT NOT NULL,
    rows_before INTEGER NOT NULL,
    rows_after INTEGER NOT NULL,
    duration_seconds REAL NOT NULL
);
"""


class Store:
    """All database access for the radar, in one small class."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # -- opportunities ------------------------------------------------

    def upsert_opportunities(self, items: list[Opportunity]) -> list[Opportunity]:
        """Insert new opportunities; refresh last_seen on known ones.

        Returns only the genuinely new items (for alerting).
        """
        now = datetime.now(timezone.utc).isoformat()
        new_items: list[Opportunity] = []
        with self._conn:
            for item in items:
                exists = self._conn.execute(
                    "SELECT 1 FROM opportunities WHERE fingerprint = ?",
                    (item.fingerprint,),
                ).fetchone()
                if exists:
                    self._conn.execute(
                        "UPDATE opportunities SET last_seen = ? WHERE fingerprint = ?",
                        (now, item.fingerprint),
                    )
                else:
                    self._conn.execute(
                        """INSERT INTO opportunities
                           (fingerprint, title, url, organization, deadline, amount,
                            location, category, source_id, tags, first_seen, last_seen)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            item.fingerprint, item.title, item.url,
                            item.organization, item.deadline, item.amount,
                            item.location, item.category, item.source_id,
                            ",".join(item.tags), now, now,
                        ),
                    )
                    new_items.append(item)
        return new_items

    def list_opportunities(self, category: str | None = None) -> list[dict]:
        query = "SELECT * FROM opportunities"
        params: tuple = ()
        if category:
            query += " WHERE category = ?"
            params = (category,)
        query += " ORDER BY first_seen DESC"
        return [dict(row) for row in self._conn.execute(query, params)]

    # -- runs ----------------------------------------------------------

    def record_run(self, run: RunRecord) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT INTO runs (source_id, started_at, status, rows, new_rows, problems)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    run.source_id, run.started_at.isoformat(), run.status,
                    run.rows, run.new_rows, run.problems,
                ),
            )

    def recent_runs(self, limit: int = 50) -> list[dict]:
        return [
            dict(row)
            for row in self._conn.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
            )
        ]

    # -- healing events ------------------------------------------------

    def record_healing(self, event: HealingEvent) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT INTO healing_events
                   (source_id, collector_id, triggered_at, diagnosis, outcome,
                    rows_before, rows_after, duration_seconds)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.source_id, event.collector_id,
                    event.triggered_at.isoformat(), event.diagnosis,
                    event.outcome, event.rows_before, event.rows_after,
                    event.duration_seconds,
                ),
            )

    def healing_log(self, limit: int = 20) -> list[dict]:
        return [
            dict(row)
            for row in self._conn.execute(
                "SELECT * FROM healing_events ORDER BY id DESC LIMIT ?", (limit,)
            )
        ]
