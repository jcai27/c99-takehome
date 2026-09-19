"""Atomic, idempotent, validated downloads.

Every fetch task in the scraper workflow goes through `fetch_with_cache`:
stream to a temp file, hash and size it as it downloads, validate the content
actually looks like what we asked for, then atomically rename into place and
write a metadata sidecar next to it. A file only exists at its final path once
it has been fully downloaded and validated, so a crash or a retry mid-download
can never leave a corrupt or partial payload where Part 2 would find it.

Re-running against a destination that already has both the payload and its
sidecar skips the network call entirely -- reruns are cheap and don't hammer
usitc.gov.
"""

import hashlib
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import httpx

DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0)


class ValidationError(Exception):
    """Raised when a downloaded payload doesn't look like what we asked for."""


@dataclass
class FetchMeta:
    url: str
    path: str
    sha256: str
    size_bytes: int
    http_status: int
    fetched_at: str
    duration_ms: int
    cached: bool = False

    def to_json(self) -> dict:
        return asdict(self)


def _meta_path(dest: Path) -> Path:
    return dest.with_name(dest.name + ".meta.json")


def _cleanup_stray_temp_files(dest: Path) -> None:
    for stray in dest.parent.glob(f"{dest.name}.tmp-*"):
        stray.unlink(missing_ok=True)


def validate_json_list(path: Path) -> None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValidationError(f"not valid JSON: {e}") from e
    if not isinstance(data, list) or len(data) == 0:
        raise ValidationError("expected a non-empty JSON array")


def validate_pdf(path: Path) -> None:
    with open(path, "rb") as f:
        header = f.read(5)
    if header != b"%PDF-":
        raise ValidationError(f"expected a PDF, got header {header!r}")


def fetch_with_cache(
    client: httpx.Client,
    url: str,
    dest: Path,
    *,
    validate: Callable[[Path], None],
) -> FetchMeta:
    """Download `url` to `dest` unless it's already there (payload + sidecar).

    Returns the metadata sidecar either way, with `cached` set accordingly.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    meta_path = _meta_path(dest)

    if dest.exists() and meta_path.exists():
        cached = FetchMeta(**json.loads(meta_path.read_text(encoding="utf-8")))
        cached.cached = True
        return cached

    _cleanup_stray_temp_files(dest)
    tmp = dest.with_name(f"{dest.name}.tmp-{uuid.uuid4().hex}")

    started = time.monotonic()
    sha256 = hashlib.sha256()
    size = 0
    status = 0
    try:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            status = resp.status_code
            with open(tmp, "wb") as f:
                for chunk in resp.iter_bytes():
                    f.write(chunk)
                    sha256.update(chunk)
                    size += len(chunk)

        validate(tmp)
        os.replace(tmp, dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    meta = FetchMeta(
        url=url,
        path=str(dest),
        sha256=sha256.hexdigest(),
        size_bytes=size,
        http_status=status,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    meta_path.write_text(json.dumps(meta.to_json(), indent=2), encoding="utf-8")
    return meta


def atomic_write_json(dest: Path, data: dict) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.tmp-{uuid.uuid4().hex}")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, dest)
