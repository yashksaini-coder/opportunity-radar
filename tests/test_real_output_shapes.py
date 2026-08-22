"""Tests against the real output shapes observed from live collectors.

Each fixture is a trimmed copy of actual `brightdata scraper run` output
from the three production collectors (MLH events, Scholars4Dev,
Python.org jobs) — the shapes that drove the flattening and cleanup
logic.
"""

import json

from radar.brightdata import _parse_rows
from radar.models import rows_to_opportunities

MLH_SHAPE = json.dumps([{
    "events": [
        {"title": "HackPrix Season 3", "url": "https://s3.hackprix.tech/",
         "start_date": "JUN 13", "end_date": "14",
         "location": "Hyderabad, Telangana, IN", "event_type": "In-Person"},
        {"title": "JAMHacks 10", "url": "https://jamhacks.ca/",
         "start_date": "JUN 12", "end_date": "14",
         "location": "Waterloo, Ontario, CA", "event_type": "In-Person"},
    ],
    "input": {"url": "https://www.mlh.com/seasons/2026/events"},
}])

S4D_SHAPE = json.dumps([
    {"scholarships": [], "product_page_url": "https://example.org/a",
     "input": {"url": "https://www.scholars4dev.com/"}},
    {"scholarships": [
        {"title": "Foreign Fulbright Student Program",
         "url": "https://www.scholars4dev.com/2876/",
         "description": "(USA) The Fulbright Program are full scholarships..."},
     ],
     "product_page_url": "https://example.org/b",
     "input": {"url": "https://www.scholars4dev.com/"}},
])

PY_SHAPE = json.dumps([
    {"title": "Senior Python Engineer\n              \n\t      \n              EPAM",
     "url": "https://www.python.org/jobs/8117/",
     "company": "Senior Python Engineer  EPAM",
     "location": "Miami Shores, FL, United States",
     "posted_date": "2026-07-23T00:00:00.000Z",
     "job_types": ["Back end"],
     "input": {"url": "https://www.python.org/jobs/"}},
])


def test_mlh_rows_are_unwrapped_from_events_key():
    rows = _parse_rows(MLH_SHAPE)
    assert len(rows) == 2
    assert rows[0]["title"] == "HackPrix Season 3"
    assert "input" not in rows[0]


def test_mlh_start_date_becomes_iso_deadline():
    rows = _parse_rows(MLH_SHAPE)
    opportunities, errors = rows_to_opportunities(rows, "mlh-hackathons", "hackathon")
    assert not errors
    assert opportunities[0].deadline is not None
    assert "-06-1" in opportunities[0].deadline  # JUN 13 → ISO June date


def test_s4d_empty_wrappers_are_dropped_and_rows_kept():
    rows = _parse_rows(S4D_SHAPE)
    assert len(rows) == 1  # empty wrapper contributes nothing
    opportunities, errors = rows_to_opportunities(rows, "s4d", "scholarship")
    assert not errors
    assert opportunities[0].title == "Foreign Fulbright Student Program"
    assert opportunities[0].location == "USA"  # from '(USA) ...' description


def test_python_jobs_title_and_company_are_cleaned():
    rows = _parse_rows(PY_SHAPE)
    opportunities, errors = rows_to_opportunities(rows, "python-jobs", "job")
    assert not errors
    opp = opportunities[0]
    assert opp.title == "Senior Python Engineer"
    assert opp.organization == "EPAM"
    assert opp.deadline is None          # posted_date is not a deadline
    assert opp.tags == ["Back end"]
