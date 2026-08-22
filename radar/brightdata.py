"""Thin wrapper around the Bright Data CLI (`brightdata`).

Every Scraper Studio interaction in this project goes through the CLI,
exactly as the hackathon intends: create/run/heal from a coding agent
or a pipeline, never from a dashboard. This module shells out to the
CLI and returns parsed JSON, keeping subprocess handling in one place.

Requires `npx -p @brightdata/cli` (or a global install) and either a
completed `brightdata login` or BRIGHTDATA_API_KEY in the environment.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

RUN_TIMEOUT_SECONDS = 600
HEAL_TIMEOUT_SECONDS = 1800


class BrightDataError(RuntimeError):
    """The CLI failed or returned output we could not parse."""


def _cli_base() -> list[str]:
    """Prefer a globally installed `brightdata`, fall back to npx."""
    if shutil.which("brightdata"):
        return ["brightdata"]
    if shutil.which("bdata"):
        return ["bdata"]
    return ["npx", "-y", "-p", "@brightdata/cli", "brightdata"]


def _run_cli(args: list[str], timeout: int) -> str:
    command = _cli_base() + args
    logger.info("CLI: %s", " ".join(command))
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise BrightDataError(f"CLI timed out after {timeout}s: {args[:2]}") from exc
    except FileNotFoundError as exc:
        raise BrightDataError(
            "Bright Data CLI not found. Install Node.js, then run "
            "`npx -p @brightdata/cli brightdata login`."
        ) from exc
    if completed.returncode != 0:
        raise BrightDataError(
            f"CLI exited {completed.returncode}: {completed.stderr.strip()[:500]}"
        )
    return completed.stdout


def run_scraper(collector_id: str, url: str) -> list[dict[str, Any]]:
    """Execute a Scraper Studio collector and return its rows.

    Uses `brightdata scraper run <id> <url> --json`; the CLI handles
    realtime-vs-batch fallback itself.
    """
    stdout = _run_cli(
        ["scraper", "run", collector_id, url, "--json"],
        timeout=RUN_TIMEOUT_SECONDS,
    )
    return _parse_rows(stdout)


def heal_scraper(
    collector_id: str, diagnosis: str, url: str, auto_approve: bool = True
) -> str:
    """Ask Scraper Studio to repair a broken collector.

    `diagnosis` is a natural-language description of what broke —
    we generate it from the validation report so the healer gets a
    precise, factual prompt. Returns the CLI's raw response text.
    """
    args = ["scraper", "heal", collector_id, diagnosis, "--url", url,
            "--timeout", str(HEAL_TIMEOUT_SECONDS)]
    if auto_approve:
        args.append("--auto-approve")
    return _run_cli(args, timeout=HEAL_TIMEOUT_SECONDS + 60)


def _parse_rows(stdout: str) -> list[dict[str, Any]]:
    """Parse CLI output into a flat list of row dicts.

    The CLI prints a JSON array, but collectors differ in shape (all
    seen in real runs): flat rows; rows nested under a list key like
    "events" or "scholarships"; and wrapper elements that carry only
    an "input" echo and empty nested lists. Flatten all of them.
    """
    text = stdout.strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            raise BrightDataError(
                f"Could not find JSON array in CLI output: {text[:200]}..."
            )
        parsed = json.loads(text[start : end + 1])
    if isinstance(parsed, dict):
        parsed = parsed.get("data", parsed.get("results", [parsed]))
    if not isinstance(parsed, list):
        raise BrightDataError(f"Unexpected CLI output shape: {type(parsed).__name__}")

    rows: list[dict[str, Any]] = []
    for element in parsed:
        if isinstance(element, dict):
            rows.extend(_flatten_element(element))
    return rows


_ROW_MARKERS = ("title", "url", "link", "name")


def _flatten_element(element: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn one top-level element into zero or more row dicts."""
    nested = [
        value for key, value in element.items()
        if isinstance(value, list) and value and all(isinstance(x, dict) for x in value)
    ]
    if nested:  # e.g. {"events": [...]} or {"scholarships": [...]}
        return [
            {k: v for k, v in row.items() if k != "input"}
            for rows in nested for row in rows
        ]
    has_empty_list = any(
        isinstance(v, list) and not v for k, v in element.items() if k != "input"
    )
    if has_empty_list and not any(k in element for k in _ROW_MARKERS):
        return []  # wrapper that crawled a page with no listings
    return [{k: v for k, v in element.items() if k != "input"}]
