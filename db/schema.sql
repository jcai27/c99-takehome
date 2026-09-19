-- Chapter 99 — schema.
--
-- Script to seed database schema. Should be runnable from a clean install.
-- Should define the schema needed for parts 1, 2, and 3.
--
-- Rerunnable: it drops what it creates first, so applying it twice is safe.
-- Postgres has no CREATE OR REPLACE TABLE, so a clean schema means dropping.
-- That also means applying this wipes your parsed data; it is a schema reset,
-- not a migration. Postgres holds the *current* structured view of the
-- latest revision Part 2 parsed -- history of raw fetches lives in
-- data/runs/, not here.
--
--   ./setup.sh
--
-- Order matters on the way down: children reference parents.

BEGIN;

DROP MATERIALIZED VIEW IF EXISTS hts_coverage;
DROP TABLE IF EXISTS rule_note_ref CASCADE;
DROP TABLE IF EXISTS note CASCADE;
DROP TABLE IF EXISTS rule_edge CASCADE;
DROP TABLE IF EXISTS rule CASCADE;
DROP TABLE IF EXISTS hts_base CASCADE;
DROP TABLE IF EXISTS import_run CASCADE;

-- One row per parser run. Append-only, unlike the tables below -- a small,
-- cheap history of "when did we last import, from which revision" even
-- though hts_base/rule themselves only ever reflect the latest run.
CREATE TABLE import_run (
  id            serial PRIMARY KEY,
  revision      text NOT NULL,
  manifest_path text NOT NULL,
  imported_at   timestamptz NOT NULL DEFAULT now()
);

-- Chapters 1-97: what Chapter 99 points back at.
--
-- The source export is a flat list that encodes a hierarchy via indent
-- level: a heading ("0101") or subheading ("0101.90") is its own row with no
-- rate of its own, and roughly half of all leaf rows are 10-digit
-- statistical suffixes (e.g. "0101.21.00.10") that carry no rate of their
-- own either -- they inherit it from their 8-digit legal ancestor. Both
-- cases are modeled here rather than left as unresolved NULLs: is_group
-- distinguishes a true legal grouping row (never itself declarable) from a
-- real line whose rate was inherited (rate_inherited = true).
CREATE TABLE hts_base (
  hts             text PRIMARY KEY,
  parent_hts      text REFERENCES hts_base(hts),
  indent          int NOT NULL,
  description     text NOT NULL,
  is_group        boolean NOT NULL DEFAULT false,
  rate_kind       text CHECK (rate_kind IN ('free','ad_valorem','specific','other')),
  mfn_rate_pct    numeric,
  rate_text       text,
  rate_inherited  boolean NOT NULL DEFAULT false
);

CREATE INDEX hts_base_parent_idx ON hts_base (parent_hts);

-- Chapter 99 provisions. rate_kind is the operator, rate_value the operand:
-- 'additive' with 25 means "base rate + 25", which a single numeric column
-- could not express.
--
-- Same flat-list-encodes-a-hierarchy structure as hts_base, but here the
-- ancestor text isn't just cosmetic: an exclusion clause (e.g. "Except for
-- products described in headings 9903.01.11, ...") is often stated once on
-- a headerless ancestor row and inherited in *legal effect* by every child
-- heading under it. context_text is the ancestor chain's text concatenated
-- with this row's own text, in document order -- it's what reference and
-- exclusion extraction runs against, and it's what a UI should show as the
-- provision's full scope, not `description` alone.
CREATE TABLE rule (
  hts           text PRIMARY KEY,
  parent_hts    text REFERENCES rule(hts),
  indent        int NOT NULL,
  subchapter    text NOT NULL,
  description   text NOT NULL,
  context_text  text NOT NULL,
  rate_kind     text NOT NULL
    CHECK (rate_kind IN ('free','additive','ad_valorem','no_change','specific','other')),
  rate_value    numeric,
  rate_text     text,
  special_text  text,
  other_text    text,
  note_ref      text
);

CREATE INDEX rule_parent_idx ON rule (parent_hts);
CREATE INDEX rule_subchapter_idx ON rule (subchapter);

-- The two relationships Chapter 99 states in prose.
--
-- target_hts is deliberately not a foreign key: a provision can name a base
-- code that no longer exists in the current revision, and those are worth
-- recording rather than dropping.
CREATE TABLE rule_edge (
  source_hts text NOT NULL REFERENCES rule(hts) ON DELETE CASCADE,
  edge_type  text NOT NULL CHECK (edge_type IN ('references','excludes')),
  target_hts text NOT NULL,
  PRIMARY KEY (source_hts, edge_type, target_hts)
);

CREATE INDEX rule_edge_target_idx ON rule_edge (target_hts, edge_type);

-- U.S. Notes and Statistical Notes, scoped to the whole chapter or to one
-- subchapter. Note numbering resets per (scope_type, subchapter, note_type)
-- -- "U.S. note 2" in subchapter II is unrelated to "U.S. note 2" in
-- subchapter III, so that triple, not a bare number, is the natural key.
CREATE TABLE note (
  id          serial PRIMARY KEY,
  scope_type  text NOT NULL CHECK (scope_type IN ('chapter','subchapter')),
  subchapter  text,
  note_type   text NOT NULL CHECK (note_type IN ('us','statistical')),
  number      int NOT NULL,
  text        text NOT NULL,
  CHECK ((scope_type = 'chapter') = (subchapter IS NULL)),
  UNIQUE (scope_type, subchapter, note_type, number)
);

-- Many-to-many: a rule can cite several notes (a real record can cite both a
-- statistical note and a different subchapter's U.S. note at once), and a
-- note can be cited by many rules. note_ref on `rule` stays as a quick
-- human-readable summary; this is the queryable/navigable version.
CREATE TABLE rule_note_ref (
  rule_hts text NOT NULL REFERENCES rule(hts) ON DELETE CASCADE,
  note_id  int  NOT NULL REFERENCES note(id) ON DELETE CASCADE,
  PRIMARY KEY (rule_hts, note_id)
);

-- Fuzzy substring search over descriptions (Part 3's search box), without a
-- separate search service.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX hts_base_description_trgm_idx ON hts_base USING gin (description gin_trgm_ops);
CREATE INDEX rule_context_text_trgm_idx ON rule USING gin (context_text gin_trgm_ops);

-- Precomputed for Part 3: which base codes have any Chapter 99 exposure at
-- all, and roughly what kind. The per-code deep query (given one hts, which
-- rules apply) is already a cheap indexed lookup and stays live; this view
-- exists because the *aggregate* question -- asked on every visit to the
-- search/landing page -- would otherwise mean scanning the full reference
-- graph against all 23k+ base codes on every request.
--
-- Matching is citation-precision-aware, not exact-equality: a rule can cite
-- a base code at 8-digit precision ("0402.29.50") while the actual hts_base
-- row is stored 10-digit ("0402.29.50.00") -- a real, common shape in the
-- source data, not a data error. Exact-equality matching alone resolves
-- only ~13% of real reference edges; this resolves ~98%.
--
-- Kept true by workflows/parser.py's `finalize` task, which REFRESHes this
-- after every load commits -- the same idempotent run that reloads the base
-- tables also refreshes what's derived from them.
CREATE MATERIALIZED VIEW hts_coverage AS
SELECT hb.hts,
       count(DISTINCT re.source_hts)                         AS rule_count,
       array_agg(DISTINCT r.subchapter ORDER BY r.subchapter) AS subchapters
FROM hts_base hb
JOIN rule_edge re ON re.edge_type = 'references'
                  AND (re.target_hts = hb.hts OR hb.hts LIKE re.target_hts || '.%')
JOIN rule r        ON r.hts = re.source_hts
WHERE hb.is_group = false
GROUP BY hb.hts;

CREATE UNIQUE INDEX hts_coverage_hts_idx ON hts_coverage (hts);

COMMIT;
