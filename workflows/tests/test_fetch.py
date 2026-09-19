"""
Unit tests for lib/fetch.py -- the download/cache/validate/atomic-write
mechanism every scraper task shares.

No network, no Docker, no Hatchet: httpx.MockTransport stands in for
usitc.gov, so these run in milliseconds and are what a CI job would run.

    uv run pytest

These cover the same scenarios verified by hand against the live stack while
building Part 1 (idempotent reruns, a missing payload/sidecar forcing a
re-fetch, a bad response never being committed) -- as fast, deterministic
regression tests instead of one-off manual checks.
"""

import json

import httpx
import pytest

from lib.fetch import (
    ValidationError,
    atomic_write_json,
    fetch_with_cache,
    validate_json_list,
    validate_pdf,
)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_downloads_validates_and_writes_sidecar(tmp_path):
    payload = json.dumps([{"htsno": "0101.21.00"}]).encode()

    def handler(request):
        return httpx.Response(200, content=payload)

    dest = tmp_path / "chapter99.json"
    with _client(handler) as client:
        meta = fetch_with_cache(client, "https://example/x", dest, validate=validate_json_list)

    assert dest.read_bytes() == payload
    assert meta.cached is False
    assert meta.size_bytes == len(payload)
    assert meta.http_status == 200
    assert (tmp_path / "chapter99.json.meta.json").exists()


def test_second_fetch_is_cached_and_skips_the_network(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, content=b'[{"a": 1}]')

    dest = tmp_path / "x.json"
    with _client(handler) as client:
        first = fetch_with_cache(client, "https://example/x", dest, validate=validate_json_list)
        second = fetch_with_cache(client, "https://example/x", dest, validate=validate_json_list)

    assert calls["n"] == 1
    assert first.cached is False
    assert second.cached is True
    assert second.sha256 == first.sha256


def test_dest_present_without_sidecar_is_refetched(tmp_path):
    """Mirrors the live test: a payload file with no .meta.json is treated as
    not-yet-fetched, not as a cache hit."""
    dest = tmp_path / "x.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"stale content from an interrupted run")

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, content=b'[{"a": 1}]')

    with _client(handler) as client:
        meta = fetch_with_cache(client, "https://example/x", dest, validate=validate_json_list)

    assert calls["n"] == 1
    assert meta.cached is False
    assert dest.read_bytes() == b'[{"a": 1}]'


def test_sidecar_present_without_dest_is_refetched(tmp_path):
    """Mirrors the live test: deleting a payload but leaving its sidecar
    behind must not be mistaken for a cache hit."""
    dest = tmp_path / "x.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "x.json.meta.json").write_text(
        json.dumps(
            {
                "url": "https://example/x",
                "path": str(dest),
                "sha256": "deadbeef",
                "size_bytes": 1,
                "http_status": 200,
                "fetched_at": "2026-01-01T00:00:00Z",
                "duration_ms": 1,
            }
        )
    )

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, content=b'[{"a": 1}]')

    with _client(handler) as client:
        fetch_with_cache(client, "https://example/x", dest, validate=validate_json_list)

    assert calls["n"] == 1
    assert dest.exists()


def test_invalid_json_is_never_committed(tmp_path):
    """A 200-status maintenance/error page must not be persisted as if it
    were good data."""

    def handler(request):
        return httpx.Response(200, content=b"<html>not json</html>")

    dest = tmp_path / "bad.json"
    with _client(handler) as client:
        with pytest.raises(ValidationError):
            fetch_with_cache(client, "https://example/x", dest, validate=validate_json_list)

    assert not dest.exists()
    assert not (tmp_path / "bad.json.meta.json").exists()
    assert list(tmp_path.glob("bad.json.tmp-*")) == []


def test_empty_json_array_is_rejected(tmp_path):
    def handler(request):
        return httpx.Response(200, content=b"[]")

    dest = tmp_path / "empty.json"
    with _client(handler) as client:
        with pytest.raises(ValidationError):
            fetch_with_cache(client, "https://example/x", dest, validate=validate_json_list)

    assert not dest.exists()


def test_pdf_without_magic_bytes_is_rejected(tmp_path):
    def handler(request):
        return httpx.Response(200, content=b"not actually a pdf")

    dest = tmp_path / "notes.pdf"
    with _client(handler) as client:
        with pytest.raises(ValidationError):
            fetch_with_cache(client, "https://example/x", dest, validate=validate_pdf)

    assert not dest.exists()


def test_valid_pdf_header_is_accepted(tmp_path):
    def handler(request):
        return httpx.Response(200, content=b"%PDF-1.7\n...rest of the file...")

    dest = tmp_path / "notes.pdf"
    with _client(handler) as client:
        meta = fetch_with_cache(client, "https://example/x", dest, validate=validate_pdf)

    assert dest.exists()
    assert meta.cached is False


def test_http_error_status_raises_and_writes_nothing(tmp_path):
    def handler(request):
        return httpx.Response(503, content=b"service unavailable")

    dest = tmp_path / "x.json"
    with _client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            fetch_with_cache(client, "https://example/x", dest, validate=validate_json_list)

    assert not dest.exists()
    assert not (tmp_path / "x.json.meta.json").exists()


def test_stray_temp_file_from_a_crash_is_cleaned_up(tmp_path):
    dest = tmp_path / "x.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    stray = tmp_path / "x.json.tmp-deadbeef"
    stray.write_bytes(b"leftover from an interrupted download")

    def handler(request):
        return httpx.Response(200, content=b'[{"a": 1}]')

    with _client(handler) as client:
        fetch_with_cache(client, "https://example/x", dest, validate=validate_json_list)

    assert not stray.exists()
    assert dest.exists()


def test_atomic_write_json_overwrites_cleanly(tmp_path):
    dest = tmp_path / "manifest.json"
    atomic_write_json(dest, {"a": 1})
    atomic_write_json(dest, {"a": 2})

    assert json.loads(dest.read_text()) == {"a": 2}
    assert list(tmp_path.glob("manifest.json.tmp-*")) == []


def test_validate_json_list_rejects_a_json_object(tmp_path):
    p = tmp_path / "x.json"
    p.write_bytes(b'{"not": "a list"}')
    with pytest.raises(ValidationError):
        validate_json_list(p)
