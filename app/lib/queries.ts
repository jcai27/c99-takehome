import sql from "./db";
import type { RateKind } from "./format";

export interface HtsBaseRow {
  hts: string;
  parent_hts: string | null;
  indent: number;
  description: string;
  is_group: boolean;
  rate_kind: RateKind | null;
  mfn_rate_pct: string | null;
  rate_text: string | null;
  rate_inherited: boolean;
}

export interface RuleRow {
  hts: string;
  parent_hts: string | null;
  indent: number;
  subchapter: string;
  description: string;
  context_text: string;
  rate_kind: RateKind;
  rate_value: string | null;
  rate_text: string | null;
  special_text: string | null;
  other_text: string | null;
  note_ref: string | null;
}

export interface ApplicableRule {
  hts: string;
  subchapter: string;
  description: string;
  context_text: string;
  rate_kind: RateKind;
  rate_value: string | null;
  rate_text: string | null;
  is_excluded: boolean;
  note_count: number;
}

export interface NoteRow {
  id: number;
  scope_type: "chapter" | "subchapter";
  subchapter: string | null;
  note_type: "us" | "statistical";
  number: number;
  text: string;
}

export interface ImportRun {
  id: number;
  revision: string;
  manifest_path: string;
  imported_at: Date;
}

export interface CoverageExample {
  hts: string;
  description: string;
  rule_count: number;
  subchapters: string[];
}

export interface SearchHit {
  hts: string;
  description: string;
  rule_count: number;
}

/** The code itself plus every ancestor, root-first -- the breadcrumb. */
export async function getHtsBaseWithAncestors(code: string): Promise<HtsBaseRow[]> {
  const rows = await sql<HtsBaseRow[]>`
    WITH RECURSIVE ancestors AS (
      SELECT * FROM hts_base WHERE hts = ${code}
      UNION ALL
      SELECT hb.* FROM hts_base hb JOIN ancestors a ON hb.hts = a.parent_hts
    )
    SELECT * FROM ancestors ORDER BY indent ASC
  `;
  return rows;
}

/**
 * Every Chapter 99 rule that applies to `code`, citation-precision-aware:
 * a rule can cite an 8-digit code ("0402.29.50") that's a dot-prefix of the
 * actual 10-digit hts_base row ("0402.29.50.00") -- exact equality alone
 * misses most real matches (see SUBMISSION.md's audit section).
 */
export async function getApplicableRules(code: string): Promise<ApplicableRule[]> {
  const rows = await sql<ApplicableRule[]>`
    SELECT DISTINCT
      r.hts, r.subchapter, r.description, r.context_text,
      r.rate_kind, r.rate_value, r.rate_text,
      EXISTS (
        SELECT 1 FROM rule_edge ex
        WHERE ex.edge_type = 'excludes' AND ex.target_hts = r.hts
      ) AS is_excluded,
      (SELECT count(*)::int FROM rule_note_ref rn WHERE rn.rule_hts = r.hts) AS note_count
    FROM rule r
    JOIN rule_edge re ON re.source_hts = r.hts AND re.edge_type = 'references'
    WHERE re.target_hts = ${code} OR ${code} LIKE re.target_hts || '.%'
    ORDER BY r.subchapter, r.hts
  `;
  return rows;
}

export async function getRule(hts: string): Promise<RuleRow | null> {
  const rows = await sql<RuleRow[]>`SELECT * FROM rule WHERE hts = ${hts}`;
  return rows[0] ?? null;
}

/** The real hts_base rows a rule's own reference edges resolve to. */
export async function getRuleReferences(
  hts: string,
): Promise<{ target_hts: string; resolved: HtsBaseRow[] }[]> {
  const targets = await sql<{ target_hts: string }[]>`
    SELECT DISTINCT target_hts FROM rule_edge
    WHERE source_hts = ${hts} AND edge_type = 'references'
    ORDER BY target_hts
  `;
  const out = [];
  for (const { target_hts } of targets) {
    const resolved = await sql<HtsBaseRow[]>`
      SELECT * FROM hts_base
      WHERE hts = ${target_hts} OR hts LIKE ${target_hts} || '.%'
      ORDER BY hts
    `;
    out.push({ target_hts, resolved });
  }
  return out;
}

export async function getRuleExcludes(hts: string): Promise<RuleRow[]> {
  return sql<RuleRow[]>`
    SELECT r.* FROM rule r
    JOIN rule_edge re ON re.target_hts = r.hts AND re.edge_type = 'excludes'
    WHERE re.source_hts = ${hts}
    ORDER BY r.hts
  `;
}

export async function getRuleExcludedBy(hts: string): Promise<RuleRow[]> {
  return sql<RuleRow[]>`
    SELECT r.* FROM rule r
    JOIN rule_edge re ON re.source_hts = r.hts AND re.edge_type = 'excludes'
    WHERE re.target_hts = ${hts}
    ORDER BY r.hts
  `;
}

export async function getRuleNotes(hts: string): Promise<NoteRow[]> {
  return sql<NoteRow[]>`
    SELECT n.* FROM note n
    JOIN rule_note_ref rn ON rn.note_id = n.id
    WHERE rn.rule_hts = ${hts}
    ORDER BY n.scope_type, n.subchapter NULLS FIRST, n.note_type, n.number
  `;
}

export async function getLatestImportRun(): Promise<ImportRun | null> {
  const rows = await sql<ImportRun[]>`
    SELECT * FROM import_run ORDER BY imported_at DESC LIMIT 1
  `;
  return rows[0] ?? null;
}

/** A handful of codes with real Chapter 99 exposure, for the landing page's
 * empty state -- so a first-time search isn't a dead end.
 *
 * Plain "highest rule_count" picks near-duplicates: dozens of codes share
 * the exact same subchapter combination (e.g. a price-bracket family all
 * pointing at the same set of provisions), so a naive top-N is six copies
 * of the same story. DISTINCT ON the subchapter combination first gets one
 * representative per distinct "kind" of coverage, then ranks those by size. */
export async function getCoverageExamples(limit = 6): Promise<CoverageExample[]> {
  return sql<CoverageExample[]>`
    SELECT hts, description, rule_count, subchapters FROM (
      SELECT DISTINCT ON (hc.subchapters)
        hc.hts, hb.description, hc.rule_count, hc.subchapters
      FROM hts_coverage hc
      JOIN hts_base hb ON hb.hts = hc.hts
      ORDER BY hc.subchapters, hc.rule_count DESC
    ) diversified
    ORDER BY rule_count DESC
    LIMIT ${limit}
  `;
}

/** Fuzzy substring search over base-schedule descriptions and codes. */
export async function searchHtsBase(query: string, limit = 25): Promise<SearchHit[]> {
  const q = query.trim();
  if (!q) return [];
  return sql<SearchHit[]>`
    SELECT hb.hts, hb.description, coalesce(hc.rule_count, 0)::int AS rule_count
    FROM hts_base hb
    LEFT JOIN hts_coverage hc ON hc.hts = hb.hts
    WHERE hb.is_group = false
      AND (hb.hts LIKE ${q + "%"} OR hb.description ILIKE ${"%" + q + "%"})
    ORDER BY hc.rule_count DESC NULLS LAST, hb.hts
    LIMIT ${limit}
  `;
}
