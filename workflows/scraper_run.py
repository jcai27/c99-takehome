"""
Trigger the Chapter99Scraper workflow and print what comes back.

    uv run python -m scraper_run

Needs the worker running in another terminal (or via ./dev.sh from the repo
root). Blocks until the run finishes; raises if it failed.
"""

from scraper import ManifestResult, ScraperInput, scraper_workflow


def main() -> None:
    result = scraper_workflow.run(ScraperInput())

    manifest = ManifestResult.model_validate(result["write_manifest"])
    print(f"revision={manifest.revision}")
    print(f"manifest={manifest.manifest_path}")

    for task_name in ("fetch_chapter99", "fetch_base_schedule", "fetch_notes_pdf"):
        r = result[task_name]
        tag = "cached" if r["cached"] else "fetched"
        print(
            f"  {r['source']:<14} {tag:<7} {r['size_bytes']:>10} bytes"
            f"  sha256={r['sha256'][:12]}  {r['path']}"
        )


if __name__ == "__main__":
    main()
