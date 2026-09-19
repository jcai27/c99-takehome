"""
Trigger the Chapter99Parser workflow and print what comes back.

    uv run python -m parser_run

Needs the worker running (or ./dev.sh) and a completed scraper run --
reads data/latest.json, touches no network. Blocks until the run finishes;
raises if it failed.
"""

from parser import FinalizeResult, ParserInput, parser_workflow


def main() -> None:
    result = parser_workflow.run(ParserInput())

    summary = FinalizeResult.model_validate(result["finalize"])
    print(f"revision={summary.revision}")
    print(f"hts_base        {summary.hts_base_rows:>8} rows")
    print(f"rule            {summary.rule_rows:>8} rows")
    print(f"note            {summary.note_rows:>8} rows")
    print(f"rule_edge       {summary.reference_edges:>8} references, {summary.exclude_edges} excludes")
    print(f"rule_note_ref   {summary.rule_note_refs:>8} links")


if __name__ == "__main__":
    main()
