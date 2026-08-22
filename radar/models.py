"""Typed models shared across the pipeline."""

from __future__ import annotations

import hashlib
import re
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
            title = _clean_title(str(row.get("title") or ""))
            valid.append(
                Opportunity(
                    title=title,
                    url=str(row.get("url") or row.get("link") or ""),
                    organization=_clean_org(
                        _opt_str(row, "organization", "host", "company"), title
                    ),
                    deadline=_normalize_deadline(
                        _opt_str(row, "deadline", "submission_deadline",
                                 "application_deadline", "start_date")
                    ),
                    amount=_opt_str(row, "amount", "prize", "prize_amount", "stipend", "salary"),
                    location=_opt_str(row, "location") or _location_from_description(row),
                    category=category,
                    source_id=source_id,
                    tags=[str(t) for t in row.get("tags") or row.get("themes")
                          or row.get("job_types") or []],
                )
            )
        except ValueError as exc:
            errors.append(f"row {index}: {exc}")
    return valid, errors


def _clean_title(raw: str) -> str:
    """First non-empty line, whitespace collapsed.

    Some collectors glue the company under the title across newlines
    ('Senior Python Engineer\\n ... \\n EPAM'); the real title is line 1.
    """
    for line in raw.splitlines():
        cleaned = " ".join(line.split())
        if cleaned:
            return cleaned
    return ""


def _clean_org(org: Optional[str], title: str) -> Optional[str]:
    """Collapse whitespace; strip a duplicated title prefix.

    Real output seen: company='Senior Python Engineer  EPAM' when
    title='Senior Python Engineer' — the org is what remains.
    """
    if not org:
        return None
    cleaned = " ".join(org.split())
    if title and cleaned.lower().startswith(title.lower()):
        cleaned = cleaned[len(title):].strip(" -·|")
    return cleaned or None


_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"])}
_MONTH_DAY_RE = re.compile(r"^([A-Za-z]{3,9})\.?\s+(\d{1,2})$")


def _normalize_deadline(raw: Optional[str]) -> Optional[str]:
    """Turn 'JUN 13'-style dates (no year) into ISO dates.

    The year is inferred: current year, rolled forward when the date
    would be more than ~6 weeks in the past (listing sites publish
    upcoming dates). Anything already parseable is passed through.
    """
    if not raw:
        return None
    value = raw.strip()
    match = _MONTH_DAY_RE.match(value)
    if not match:
        return value
    month = _MONTHS.get(match.group(1).lower()[:3])
    day = int(match.group(2))
    if not month or not 1 <= day <= 31:
        return value
    today = datetime.now(timezone.utc).date()
    try:
        candidate = today.replace(month=month, day=day)
    except ValueError:
        return value
    if (today - candidate).days > 45:
        candidate = candidate.replace(year=candidate.year + 1)
    return candidate.isoformat()


_PAREN_PREFIX_RE = re.compile(r"^\(([^)]{2,40})\)")


def _location_from_description(row: dict[str, Any]) -> Optional[str]:
    """Scholarship feeds often lead the description with '(UK) …'."""
    description = row.get("description")
    if not isinstance(description, str):
        return None
    match = _PAREN_PREFIX_RE.match(description.strip())
    return match.group(1) if match else None


def _opt_str(row: dict[str, Any], *keys: str) -> Optional[str]:
    """First non-empty value among aliased keys, as a stripped string."""
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None
