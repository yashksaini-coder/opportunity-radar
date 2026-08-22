"""Configuration loading: sources.yaml + environment.

Sources are validated at load time: http(s) URLs only, unique ids,
and no government/military domains (disallowed by the hackathon rules)
— a typo in sources.yaml fails fast with a clear message instead of
producing a confusing scraper error later.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml

_BLOCKED_DOMAIN_SUFFIXES = (".gov", ".mil", ".gov.in", ".nic.in", ".gov.uk", ".gc.ca")
_SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
_COLLECTOR_ID_RE = re.compile(r"^c_[A-Za-z0-9]+$")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCES_PATH = PROJECT_ROOT / "config" / "sources.yaml"
EXTRA_SOURCES_PATH = PROJECT_ROOT / "config" / "sources.extra.yaml"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "radar.db"
DOTENV_PATH = PROJECT_ROOT / ".env"


def _load_dotenv(path: Path | None = None) -> None:
    """Populate os.environ from .env, without overriding real env vars.

    Keeps the README's `cp .env.example .env` promise true for local runs.
    Platform-injected variables (GitHub Actions secrets, Render config)
    already live in os.environ and always win over the file.
    """
    dotenv = path or DOTENV_PATH
    if not dotenv.exists():
        return
    for line in dotenv.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


@dataclass(frozen=True)
class Source:
    """One scrape target backed by a Scraper Studio collector."""

    id: str
    name: str
    url: str
    collector_id: str
    category: str
    description: str

    @property
    def is_configured(self) -> bool:
        return bool(self.collector_id.strip())


@dataclass(frozen=True)
class HealthThresholds:
    """Limits that decide whether a run is healthy or needs healing."""

    min_rows: int = 3
    max_null_ratio: float = 0.4
    required_fields: tuple[str, ...] = ("title", "url")


@dataclass(frozen=True)
class Settings:
    sources: tuple[Source, ...] = ()
    health: HealthThresholds = field(default_factory=HealthThresholds)
    db_path: Path = DEFAULT_DB_PATH
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    auto_approve_heals: bool = True


def load_settings(sources_path: Path | None = None) -> Settings:
    """Load sources.yaml and environment variables into Settings.

    Raises FileNotFoundError with a helpful message if the config is
    missing, and ValueError if it is malformed.
    """
    _load_dotenv()
    path = sources_path or DEFAULT_SOURCES_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Copy config/sources.yaml and fill in your "
            "collector IDs from `brightdata scraper create`."
        )

    raw = yaml.safe_load(path.read_text()) or {}
    raw_sources = list(raw.get("sources") or [])
    if not raw_sources:
        raise ValueError(f"{path} defines no sources.")

    # Sources added from the dashboard live in a separate file so the
    # hand-edited sources.yaml (and its comments) are never rewritten.
    extra_path = path.parent / EXTRA_SOURCES_PATH.name
    if extra_path.exists():
        extra = yaml.safe_load(extra_path.read_text()) or {}
        raw_sources.extend(extra.get("sources") or [])

    sources = tuple(
        Source(
            id=str(entry["id"]),
            name=str(entry.get("name", entry["id"])),
            url=str(entry["url"]),
            collector_id=str(entry.get("collector_id") or ""),
            category=str(entry.get("category", "other")),
            description=" ".join(str(entry.get("description", "")).split()),
        )
        for entry in raw_sources
    )
    _validate_sources(sources)

    health_raw = raw.get("health") or {}
    health = HealthThresholds(
        min_rows=int(health_raw.get("min_rows", 3)),
        max_null_ratio=float(health_raw.get("max_null_ratio", 0.4)),
        required_fields=tuple(health_raw.get("required_fields", ["title", "url"])),
    )

    return Settings(
        sources=sources,  # validated above
        health=health,
        db_path=Path(os.environ.get("RADAR_DB_PATH", DEFAULT_DB_PATH)),
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        auto_approve_heals=os.environ.get("RADAR_AUTO_APPROVE", "1") == "1",
    )


def make_source_from_url(
    url: str, existing_ids: set[str], category: str = "other"
) -> Source:
    """Build a valid Source from a bare URL (dashboard 'Add source').

    Validates the URL the same way sources.yaml is validated and derives
    a unique slug id from the hostname. Raises ValueError on bad input.
    """
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("enter a full http(s) URL, e.g. https://site.com/scholarships")
    host = parsed.hostname.lower()
    if any(host.endswith(suffix) for suffix in _BLOCKED_DOMAIN_SUFFIXES):
        raise ValueError("government/military sites are not allowed")

    base = (
        re.sub(r"[^a-z0-9-]", "-", host.removeprefix("www.").split(".")[0])[:40].strip(
            "-"
        )
        or "source"
    )
    slug, n = base, 2
    while slug in existing_ids:
        slug, n = f"{base}-{n}", n + 1

    source = Source(
        id=slug,
        name=host.removeprefix("www."),
        url=url,
        collector_id="",
        category=category,
        description=(
            "Extract opportunity listings: title, url, organization, "
            "deadline, amount, location."
        ),
    )
    _validate_sources((source,))
    return source


def append_extra_source(source: Source, extra_path: Path | None = None) -> None:
    """Persist a dashboard-added source to sources.extra.yaml."""
    path = extra_path or EXTRA_SOURCES_PATH
    data = {"sources": []}
    if path.exists():
        data = yaml.safe_load(path.read_text()) or {"sources": []}
        data.setdefault("sources", [])
    data["sources"].append(
        {
            "id": source.id,
            "name": source.name,
            "url": source.url,
            "collector_id": source.collector_id,
            "category": source.category,
            "description": source.description,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def _validate_sources(sources: tuple[Source, ...]) -> None:
    """Fail fast on malformed or rule-breaking scrape targets."""
    seen_ids: set[str] = set()
    for source in sources:
        if not _SOURCE_ID_RE.match(source.id):
            raise ValueError(
                f"source id '{source.id}' is invalid — use lowercase "
                "letters, digits and hyphens (2–64 chars)"
            )
        if source.id in seen_ids:
            raise ValueError(f"duplicate source id '{source.id}'")
        seen_ids.add(source.id)

        parsed = urlparse(source.url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError(
                f"source '{source.id}': url must be a full http(s) URL, "
                f"got '{source.url}'"
            )
        host = parsed.hostname.lower()
        if any(host.endswith(suffix) for suffix in _BLOCKED_DOMAIN_SUFFIXES):
            raise ValueError(
                f"source '{source.id}': scraping government/military sites "
                f"is not allowed (host '{host}')"
            )
        if source.collector_id and not _COLLECTOR_ID_RE.match(source.collector_id):
            raise ValueError(
                f"source '{source.id}': collector_id should look like "
                f"'c_abc123…', got '{source.collector_id}'"
            )
