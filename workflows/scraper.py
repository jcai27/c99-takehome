"""
The Chapter 99 scraper: fetches the three USITC sources and lands raw,
validated, unmodified payloads under DATA_DIR, with a manifest recording
where each one came from and when.

    uv run python -m scraper_run

See ../parts/PART1_SCRAPER.md for the requirements this satisfies, and
lib/fetch.py for how idempotency and atomicity are implemented.
"""

from datetime import datetime, timezone

import httpx
from hatchet_sdk import Context, Hatchet
from pydantic import BaseModel

from lib.fetch import (
    DEFAULT_TIMEOUT,
    atomic_write_json,
    fetch_with_cache,
    validate_json_list,
    validate_pdf,
)
from lib.paths import LATEST_POINTER, revision_dir

hatchet = Hatchet()

CURRENT_RELEASE_URL = "https://hts.usitc.gov/reststop/currentRelease"
CHAPTER99_URL = (
    "https://hts.usitc.gov/reststop/exportList?from=9900&to=9999&format=JSON&styles=false"
)
BASE_SCHEDULE_URL = (
    "https://hts.usitc.gov/reststop/exportList?from=0100&to=9799&format=JSON&styles=false"
)
NOTES_PDF_URL = (
    "https://hts.usitc.gov/reststop/file?release=currentRelease&filename=Chapter%2099"
)


class ScraperInput(BaseModel):
    pass


class ReleaseInfo(BaseModel):
    name: str
    description: str
    title: str


class FetchResult(BaseModel):
    source: str
    url: str
    path: str
    sha256: str
    size_bytes: int
    http_status: int
    fetched_at: str
    duration_ms: int
    cached: bool


class ManifestResult(BaseModel):
    revision: str
    manifest_path: str
    latest_path: str


scraper_workflow = hatchet.workflow(name="Chapter99Scraper", input_validator=ScraperInput)


@scraper_workflow.task(
    retries=5, backoff_factor=2.0, backoff_max_seconds=30, execution_timeout="30s"
)
def get_release(input: ScraperInput, ctx: Context) -> ReleaseInfo:
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        resp = client.get(CURRENT_RELEASE_URL)
        resp.raise_for_status()
        data = resp.json()
    ctx.log(f"current release: {data['name']} ({data['title']})")
    return ReleaseInfo(**data)


def _run_fetch(source: str, url: str, filename: str, validate, ctx: Context) -> FetchResult:
    release = ctx.task_output(get_release)
    dest = revision_dir(release.name) / filename
    with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
        meta = fetch_with_cache(client, url, dest, validate=validate)
    ctx.log(
        f"{source}: {'cached' if meta.cached else 'fetched'} "
        f"{meta.size_bytes} bytes -> {dest}"
    )
    return FetchResult(source=source, **meta.to_json())


@scraper_workflow.task(
    parents=[get_release],
    retries=5,
    backoff_factor=2.0,
    backoff_max_seconds=60,
    execution_timeout="2m",
)
def fetch_chapter99(input: ScraperInput, ctx: Context) -> FetchResult:
    return _run_fetch("chapter99", CHAPTER99_URL, "chapter99.json", validate_json_list, ctx)


@scraper_workflow.task(
    parents=[get_release],
    retries=5,
    backoff_factor=2.0,
    backoff_max_seconds=60,
    execution_timeout="5m",
)
def fetch_base_schedule(input: ScraperInput, ctx: Context) -> FetchResult:
    return _run_fetch(
        "base_schedule", BASE_SCHEDULE_URL, "base_schedule.json", validate_json_list, ctx
    )


@scraper_workflow.task(
    parents=[get_release],
    retries=5,
    backoff_factor=2.0,
    backoff_max_seconds=60,
    execution_timeout="5m",
)
def fetch_notes_pdf(input: ScraperInput, ctx: Context) -> FetchResult:
    return _run_fetch("notes_pdf", NOTES_PDF_URL, "chapter99_notes.pdf", validate_pdf, ctx)


@scraper_workflow.task(
    parents=[get_release, fetch_chapter99, fetch_base_schedule, fetch_notes_pdf],
    retries=3,
)
def write_manifest(input: ScraperInput, ctx: Context) -> ManifestResult:
    release = ctx.task_output(get_release)
    sources = {
        "chapter99": ctx.task_output(fetch_chapter99).model_dump(),
        "base_schedule": ctx.task_output(fetch_base_schedule).model_dump(),
        "notes_pdf": ctx.task_output(fetch_notes_pdf).model_dump(),
    }

    manifest_path = revision_dir(release.name) / "manifest.json"
    generated_at = datetime.now(timezone.utc).isoformat()
    atomic_write_json(
        manifest_path,
        {"revision": release.model_dump(), "generated_at": generated_at, "sources": sources},
    )

    # Only reached once all three fetches succeeded, so this is the one place
    # that advances "latest" -- a partial failure never leaves latest.json
    # pointing at an incomplete run.
    atomic_write_json(
        LATEST_POINTER,
        {
            "revision": release.name,
            "manifest_path": str(manifest_path),
            "updated_at": generated_at,
        },
    )

    ctx.log(f"manifest written: {manifest_path}")
    return ManifestResult(
        revision=release.name,
        manifest_path=str(manifest_path),
        latest_path=str(LATEST_POINTER),
    )
