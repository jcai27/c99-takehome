"""
The Chapter 99 parser: reads what the scraper landed in DATA_DIR and
structures it into Postgres. Touches no network -- everything here reads
from data/latest.json and the files its manifest points at.

    uv run python -m parser_run

See ../parts/PART2_PARSER.md for the requirements this satisfies, and
db/schema.sql for the schema and the reasoning behind it. Each load task
below re-derives whatever raw-file state it needs (mostly by calling
lib.hierarchy.resolve again) rather than passing large row sets through
Hatchet's durable task-output channel, which is sized for metadata, not bulk
data -- and rather than reading back through Postgres, which would leave
downstream tasks dependent on exactly what an upstream task chose to persist.
Idempotency is transactional: each task truncates and reloads its own
table(s) inside one DB transaction, the same "either the whole thing landed,
or none of it did" guarantee Part 1 gets from an atomic file rename.
"""

import json
from pathlib import Path

from hatchet_sdk import Context
from pydantic import BaseModel

from lib import db
from lib.hierarchy import Node, resolve
from lib.notes_pdf import extract_pages_text
from lib.notes_pdf import parse as parse_notes
from lib.paths import DATA_DIR
from lib.rates import categorize, categorize_base
from lib.refs import extract_exclusions, extract_note_refs, extract_references, subchapter_of
from scraper import hatchet


class ParserInput(BaseModel):
    pass


class ManifestInfo(BaseModel):
    revision: str
    manifest_path: str
    chapter99_path: str
    base_schedule_path: str
    notes_pdf_path: str


class LoadResult(BaseModel):
    table: str
    row_count: int


class EdgeLoadResult(BaseModel):
    references: int
    excludes: int


class FinalizeResult(BaseModel):
    revision: str
    hts_base_rows: int
    rule_rows: int
    note_rows: int
    reference_edges: int
    exclude_edges: int
    rule_note_refs: int


parser_workflow = hatchet.workflow(name="Chapter99Parser", input_validator=ParserInput)


@parser_workflow.task(retries=2)
def load_manifest(input: ParserInput, ctx: Context) -> ManifestInfo:
    latest = json.loads((DATA_DIR / "latest.json").read_text(encoding="utf-8"))
    manifest_path = Path(latest["manifest_path"])
    if not manifest_path.is_absolute():
        manifest_path = DATA_DIR / manifest_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = manifest["sources"]
    info = ManifestInfo(
        revision=manifest["revision"]["name"],
        manifest_path=str(manifest_path),
        chapter99_path=sources["chapter99"]["path"],
        base_schedule_path=sources["base_schedule"]["path"],
        notes_pdf_path=sources["notes_pdf"]["path"],
    )
    ctx.log(f"parsing revision {info.revision} from {info.manifest_path}")
    return info


def _load_json_rows(path: str) -> list[dict]:
    p = Path(path)
    if not p.is_absolute():
        p = DATA_DIR / p
    return json.loads(p.read_text(encoding="utf-8"))


def _chapter99_nodes(chapter99_path: str) -> list[Node]:
    rows = _load_json_rows(chapter99_path)
    return [n for n in resolve(rows) if n.htsno]


@parser_workflow.task(parents=[load_manifest], retries=2, execution_timeout="2m")
def load_hts_base(input: ParserInput, ctx: Context) -> LoadResult:
    manifest = ctx.task_output(load_manifest)
    rows = _load_json_rows(manifest.base_schedule_path)
    nodes = resolve(rows)
    by_htsno = {n.htsno: n for n in nodes if n.htsno}
    children_of = {n.parent_htsno for n in nodes if n.parent_htsno}

    def effective_rate(node: Node):
        seen: set[str] = set()
        cur: Node | None = node
        while cur is not None:
            rate = categorize_base(cur.raw.get("general"))
            if rate is not None:
                return rate, cur.htsno != node.htsno
            if cur.parent_htsno is None or cur.parent_htsno in seen:
                return None, False
            seen.add(cur.parent_htsno)
            cur = by_htsno.get(cur.parent_htsno)
        return None, False

    records = []
    for node in nodes:
        if not node.htsno:
            continue
        rate, inherited = effective_rate(node)
        is_group = rate is None and node.htsno in children_of
        records.append(
            (
                node.htsno,
                node.parent_htsno,
                node.indent,
                node.description,
                is_group,
                rate.kind if rate else None,
                rate.value if (rate and rate.kind == "ad_valorem") else None,
                rate.text if rate else None,
                inherited,
            )
        )

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE hts_base RESTART IDENTITY CASCADE")
            with cur.copy(
                "COPY hts_base (hts, parent_hts, indent, description, is_group, "
                "rate_kind, mfn_rate_pct, rate_text, rate_inherited) FROM STDIN"
            ) as copy:
                for rec in records:
                    copy.write_row(rec)
        conn.commit()

    ctx.log(f"hts_base: loaded {len(records)} rows")
    return LoadResult(table="hts_base", row_count=len(records))


@parser_workflow.task(parents=[load_manifest], retries=2, execution_timeout="3m")
def load_notes(input: ParserInput, ctx: Context) -> LoadResult:
    import pypdf

    manifest = ctx.task_output(load_manifest)
    pdf_path = Path(manifest.notes_pdf_path)
    if not pdf_path.is_absolute():
        pdf_path = DATA_DIR / pdf_path
    reader = pypdf.PdfReader(pdf_path)
    notes = parse_notes(extract_pages_text(reader))

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE rule_note_ref, note RESTART IDENTITY CASCADE")
            with cur.copy(
                "COPY note (scope_type, subchapter, note_type, number, text) FROM STDIN"
            ) as copy:
                for n in notes:
                    copy.write_row((n.scope_type, n.subchapter, n.note_type, n.number, n.text))
        conn.commit()

    ctx.log(f"note: loaded {len(notes)} rows")
    return LoadResult(table="note", row_count=len(notes))


@parser_workflow.task(parents=[load_manifest], retries=2, execution_timeout="2m")
def load_rules(input: ParserInput, ctx: Context) -> LoadResult:
    manifest = ctx.task_output(load_manifest)
    nodes = _chapter99_nodes(manifest.chapter99_path)

    records = []
    for node in nodes:
        subchapter = subchapter_of(node.htsno)
        # `general` is blank on ~511 real rows (price-bracket/quota
        # provisions, e.g. subchapter IV's "Valued less than 25c/kg" ladder)
        # whose actual rate lives in the source JSON's `additionalDuties`
        # field instead -- confirmed against real data, and previously
        # missed entirely, which meant these rows showed "not stated" even
        # though a real specific rate ("66.6c/kg") was sitting right there.
        rate = categorize(node.raw.get("general")) or categorize(node.raw.get("additionalDuties"))
        if rate is None:
            rate_kind, rate_value, rate_text = "other", None, None
        else:
            rate_kind, rate_value, rate_text = rate.kind, rate.value, rate.text

        note_sources = [node.context_text] + [
            (fn.get("value") or "") for fn in (node.raw.get("footnotes") or [])
        ]
        refs = set()
        for src in note_sources:
            refs.update(extract_note_refs(src, own_subchapter=subchapter))
        note_ref_summary = "; ".join(
            f"{'statistical' if t == 'statistical' else 'U.S.'} note {n}"
            + (f" to subchapter {s}" if s and s != subchapter else "")
            for t, s, n in sorted(refs, key=lambda tup: (tup[0], tup[1] or "", tup[2]))
        ) or None

        records.append(
            (
                node.htsno,
                node.parent_htsno,
                node.indent,
                subchapter,
                node.description,
                node.context_text,
                rate_kind,
                rate_value,
                rate_text,
                (node.raw.get("special") or "").strip() or None,
                (node.raw.get("other") or "").strip() or None,
                note_ref_summary,
            )
        )

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE rule_edge, rule_note_ref, rule RESTART IDENTITY CASCADE")
            with cur.copy(
                "COPY rule (hts, parent_hts, indent, subchapter, description, context_text, "
                "rate_kind, rate_value, rate_text, special_text, other_text, note_ref) FROM STDIN"
            ) as copy:
                for rec in records:
                    copy.write_row(rec)
        conn.commit()

    ctx.log(f"rule: loaded {len(records)} rows")
    return LoadResult(table="rule", row_count=len(records))


@parser_workflow.task(parents=[load_manifest, load_rules], retries=2, execution_timeout="2m")
def load_rule_edges(input: ParserInput, ctx: Context) -> EdgeLoadResult:
    manifest = ctx.task_output(load_manifest)
    nodes = _chapter99_nodes(manifest.chapter99_path)

    edges = []
    for node in nodes:
        for target in extract_references(node.context_text):
            edges.append((node.htsno, "references", target))
        for target in extract_exclusions(node.context_text):
            edges.append((node.htsno, "excludes", target))
    edges = sorted(set(edges))

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE rule_edge")
            with cur.copy(
                "COPY rule_edge (source_hts, edge_type, target_hts) FROM STDIN"
            ) as copy:
                for rec in edges:
                    copy.write_row(rec)
        conn.commit()

    references = sum(1 for _, kind, _ in edges if kind == "references")
    excludes = sum(1 for _, kind, _ in edges if kind == "excludes")
    ctx.log(f"rule_edge: {references} references, {excludes} excludes")
    return EdgeLoadResult(references=references, excludes=excludes)


@parser_workflow.task(parents=[load_manifest, load_rules, load_notes], retries=2, execution_timeout="2m")
def load_rule_notes(input: ParserInput, ctx: Context) -> LoadResult:
    manifest = ctx.task_output(load_manifest)
    nodes = _chapter99_nodes(manifest.chapter99_path)

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, scope_type, subchapter, note_type, number FROM note")
            note_ids = {
                (row[1], row[2], row[3], row[4]): row[0] for row in cur.fetchall()
            }

            links = set()
            for node in nodes:
                subchapter = subchapter_of(node.htsno)
                sources = [node.context_text] + [
                    (fn.get("value") or "") for fn in (node.raw.get("footnotes") or [])
                ]
                for src in sources:
                    for note_type, scope_sub, number in extract_note_refs(
                        src, own_subchapter=subchapter
                    ):
                        scope_type = "chapter" if scope_sub is None else "subchapter"
                        note_id = note_ids.get((scope_type, scope_sub, note_type, number))
                        if note_id is not None:
                            links.add((node.htsno, note_id))

            cur.execute("TRUNCATE TABLE rule_note_ref")
            with cur.copy("COPY rule_note_ref (rule_hts, note_id) FROM STDIN") as copy:
                for rec in sorted(links):
                    copy.write_row(rec)
        conn.commit()

    ctx.log(f"rule_note_ref: {len(links)} links")
    return LoadResult(table="rule_note_ref", row_count=len(links))


@parser_workflow.task(
    parents=[load_manifest, load_hts_base, load_rules, load_rule_edges, load_rule_notes, load_notes],
    retries=2,
)
def finalize(input: ParserInput, ctx: Context) -> FinalizeResult:
    manifest = ctx.task_output(load_manifest)
    hts_base = ctx.task_output(load_hts_base)
    rule = ctx.task_output(load_rules)
    notes = ctx.task_output(load_notes)
    edges = ctx.task_output(load_rule_edges)
    rule_notes = ctx.task_output(load_rule_notes)

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO import_run (revision, manifest_path) VALUES (%s, %s)",
                (manifest.revision, manifest.manifest_path),
            )
            # Same transaction, same idempotent run: whatever's derived from
            # the base tables never goes stale relative to what was just
            # loaded, and there's no separate refresh schedule to forget.
            cur.execute("REFRESH MATERIALIZED VIEW hts_coverage")
        conn.commit()

    ctx.log(f"import_run recorded for revision {manifest.revision}; hts_coverage refreshed")
    return FinalizeResult(
        revision=manifest.revision,
        hts_base_rows=hts_base.row_count,
        rule_rows=rule.row_count,
        note_rows=notes.row_count,
        reference_edges=edges.references,
        exclude_edges=edges.excludes,
        rule_note_refs=rule_notes.row_count,
    )
