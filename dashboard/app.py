"""Opportunity Radar dashboard — FastAPI backend.

Serves the single-page UI plus small JSON endpoints backed by the same
SQLite store the pipeline writes to. Hardened at the edges:

- per-IP rate limiting (see security.py) — floods get 429s
- validated, bounded query params — no free-form input reaches SQL
- POST /api/run is guarded: one run at a time, a cooldown between
  runs, and (for public deploys) an optional RADAR_RUN_TOKEN that
  must be presented in the X-Run-Token header
- security headers + generic 500s that never leak internals

    uvicorn dashboard.app:app --reload
"""

from __future__ import annotations

import hmac
import logging
import os
import subprocess
import sys
import time
from enum import Enum
from pathlib import Path

from fastapi import FastAPI, Header, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from radar.config import (
    PROJECT_ROOT,
    append_extra_source,
    load_settings,
    make_source_from_url,
)
from radar.store import Store

from .security import RateLimitMiddleware, SecurityHeadersMiddleware

logger = logging.getLogger(__name__)

app = FastAPI(title="Opportunity Radar", version="0.1.0", docs_url=None, redoc_url=None)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

_STATIC = Path(__file__).parent / "static"
_RUN_COOLDOWN_SECONDS = 60
_pipeline_proc: subprocess.Popen | None = None
_last_run_started = 0.0


class Category(str, Enum):
    hackathon = "hackathon"
    scholarship = "scholarship"
    internship = "internship"
    job = "job"
    other = "other"


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    """Never leak stack traces or paths to clients."""
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse({"detail": "internal error"}, status_code=500)


def _token_ok(supplied: str | None) -> bool:
    """True when no token is configured, or the supplied one matches.

    Local runs leave RADAR_RUN_TOKEN empty so the dashboard just works;
    a public deploy sets it and both mutating endpoints require it.
    """
    required = os.environ.get("RADAR_RUN_TOKEN", "")
    return not required or hmac.compare_digest(required, supplied or "")


@app.get("/api/config")
def config() -> dict:
    """What the page needs to render itself — never the token value."""
    return {"run_token_required": bool(os.environ.get("RADAR_RUN_TOKEN", ""))}


def _store() -> Store:
    """One connection per request keeps SQLite happy across threads."""
    return Store(load_settings().db_path)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


@app.get("/api/opportunities")
def opportunities(
    category: Category | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict:
    store = _store()
    try:
        items = store.list_opportunities(category.value if category else None)
    finally:
        store.close()
    return {"count": len(items), "items": items[:limit]}


@app.get("/api/health")
def health() -> dict:
    """Pipeline health: latest status per source, including configured
    sources that have never run yet (shown as 'queued')."""
    settings = load_settings()
    store = _store()
    try:
        runs = store.recent_runs(limit=100)
    finally:
        store.close()
    latest: dict[str, dict] = {}
    for run in runs:  # runs are newest-first
        latest.setdefault(run["source_id"], run)
    for source in settings.sources:
        latest.setdefault(
            source.id,
            {"source_id": source.id, "status": "queued", "rows": 0,
             "new_rows": 0, "started_at": None,
             "problems": "first run pending"},
        )
    return {"sources": list(latest.values()), "runs": runs[:30]}


class NewSource(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


@app.post("/api/sources", status_code=201)
def add_source(
    body: NewSource, x_run_token: str | None = Header(default=None)
) -> JSONResponse:
    """Register a new scrape target from the dashboard.

    The URL passes the same validation as sources.yaml (http(s) only,
    no government/military domains). The source lands in
    config/sources.extra.yaml as 'queued' until a Scraper Studio
    collector is created for it.
    """
    if not _token_ok(x_run_token):
        return JSONResponse({"detail": "run token required"}, status_code=401)

    settings = load_settings()
    try:
        source = make_source_from_url(body.url, {s.id for s in settings.sources})
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    append_extra_source(source)
    logger.info("Source added from dashboard: %s (%s)", source.id, source.url)
    return JSONResponse(
        {"id": source.id, "status": "queued",
         "next_step": f"brightdata scraper create {source.url} \"{source.description}\""},
        status_code=201,
    )


@app.post("/api/run")
def run_pipeline(x_run_token: str | None = Header(default=None)) -> JSONResponse:
    """Kick off a pipeline run in the background — guarded.

    A run costs real scraping credits, so this endpoint is the most
    protected one: rate-limited (middleware), single-flight, cooled
    down, and token-gated when RADAR_RUN_TOKEN is configured.
    """
    global _pipeline_proc, _last_run_started

    if not _token_ok(x_run_token):
        return JSONResponse({"detail": "run token required"}, status_code=401)

    if _pipeline_proc is not None and _pipeline_proc.poll() is None:
        return JSONResponse({"status": "already_running"}, status_code=409)

    elapsed = time.monotonic() - _last_run_started
    if _last_run_started and elapsed < _RUN_COOLDOWN_SECONDS:
        wait = int(_RUN_COOLDOWN_SECONDS - elapsed) + 1
        return JSONResponse(
            {"detail": f"cooldown — try again in {wait}s"},
            status_code=429,
            headers={"Retry-After": str(wait)},
        )

    _last_run_started = time.monotonic()
    _pipeline_proc = subprocess.Popen(
        [sys.executable, "-m", "radar.pipeline"], cwd=PROJECT_ROOT
    )
    return JSONResponse({"status": "started"})


@app.get("/api/run")
def run_status() -> dict:
    if _pipeline_proc is None:
        return {"running": False}
    return {"running": _pipeline_proc.poll() is None}


@app.get("/api/healing-log")
def healing_log(limit: int = Query(default=20, ge=1, le=100)) -> dict:
    store = _store()
    try:
        events = store.healing_log(limit=limit)
    finally:
        store.close()
    return {"events": events}
