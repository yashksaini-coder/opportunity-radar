"""Typed models shared across the pipeline."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class Opportunity(BaseModel):
    """One normalized opportunity row, whatever site it came from."""

    title: str
    url: str
    organization: Optional[str] = None
    deadline: Optional[str] = None  # ISO date string when parseable
    amount: Optional[str] = None    # prize / award / stipend, free text
    location: Optional[str] = None
    category: str = "other"         # hackathon | scholarship | internship | other
    source_id: str = ""
    tags: list[str] = Field(default_factory=list)

    @field_validator("title", "url")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @field_validator("url")
    @classmethod
    def _safe_url(cls, value: str) -> str:
        """Scraped data is untrusted — only allow http(s) links.

        Blocks javascript:, data:, file: and friends from ever reaching
        the dashboard's <a href> attributes.
        """
        if not value.lower().startswith(("http://", "https://")):
            raise ValueError("url must be http(s)")
        return value

    @field_validator("title")
    @classmethod
    def _bounded_title(cls, value: str) -> str:
        """Cap length so a malformed page can't bloat the store/UI."""
        return value[:300]

    @property
    def fingerprint(self) -> str:
        """Stable identity for dedupe across runs."""
        raw = f"{self.source_id}|{self.title}|{self.url}".lower()
        return hashlib.sha1(raw.encode()).hexdigest()


class ValidationReport(BaseModel):
    """Outcome of validating one scraper run."""

    healthy: bool
    rows_total: int = 0
    rows_valid: int = 0
    problems: list[str] = Field(default_factory=list)

    def diagnosis(self) -> str:
        """Human/AI-readable summary, fed to `brightdata scraper heal`."""
        return "; ".join(self.problems) if self.problems else "no problems detected"


class RunRecord(BaseModel):
    """One pipeline run of one source, for the health timeline."""

    source_id: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "ok"              # ok | healed | failed
    rows: int = 0
    new_rows: int = 0
    problems: str = ""


class HealingEvent(BaseModel):
    """A recorded self-healing intervention — the spider-sense log."""

    source_id: str
    collector_id: str
    triggered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    diagnosis: str
    outcome: str = "pending"        # healed | failed
    rows_before: int = 0
    rows_after: int = 0
    duration_seconds: float = 0.0


def rows_to_opportunities(
    rows: list[dict[str, Any]], source_id: str, category: str
) -> tuple[list[Opportunity], list[str]]:
    """Convert raw scraper output rows into validated Opportunities.

    Returns (valid_opportunities, per_row_errors). Rows that fail
    validation are reported, not silently dropped.
    """
    valid: list[Opportunity] = []
    errors: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"row {index}: not an object")
            continue
        try:
            valid.append(
                Opportunity(
                    title=str(row.get("title") or ""),
                    url=str(row.get("url") or row.get("link") or ""),
                    organization=_opt_str(row, "organization", "host", "company"),
                    deadline=_opt_str(row, "deadline", "submission_deadline", "application_deadline", "start_date"),
                    amount=_opt_str(row, "amount", "prize", "prize_amount", "stipend", "salary"),
                    location=_opt_str(row, "location"),
                    category=category,
                    source_id=source_id,
                    tags=[str(t) for t in row.get("tags") or row.get("themes") or []],
                )
            )
        except ValueError as exc:
            errors.append(f"row {index}: {exc}")
    return valid, errors


def _opt_str(row: dict[str, Any], *keys: str) -> Optional[str]:
    """First non-empty value among aliased keys, as a stripped string."""
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None
