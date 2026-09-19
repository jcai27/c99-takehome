# Chapter 99 Explorer

Part 3: a Next.js (App Router, TypeScript) app over the Postgres schema
Parts 1 and 2 built. Read-only, no auth.

## The idea

Pick a base HTS code (chapters 1-97) and see every Chapter 99 provision that
currently touches it, in one place: its resolved rate, whether something
else excludes it, and the notes that explain why -- with a citation back to
the source revision. That's the whole product; see the root
[`SUBMISSION.md`](../SUBMISSION.md) for why this scope and not a
browse-everything catalog.

## Running it

```bash
./dev.sh                  # from the repo root, or:
docker compose up -d      # just Postgres and Hatchet
cd app && npm install && npm run dev   # -> http://localhost:3000
```

Needs a database that's already been through Parts 1 and 2 (`scraper_run`
then `parser_run`) -- an empty schema will just show empty search results and
"no Chapter 99 provision on record" everywhere, which is the correct (if
uninteresting) behavior, not a bug.

Connects to `DATABASE_URL` the same way the rest of the stack does --
defaults in `.env.example`, matching `docker-compose.yaml`.

## Pages

| Route | What it is |
| --- | --- |
| `/` | Search by HTS code or product description; a landing state showing codes with real Chapter 99 exposure (most codes have none -- see below) |
| `/hts/[code]` | The core page: hierarchy breadcrumb, the code's own resolved MFN rate, and a sortable/filterable table of every applicable Chapter 99 provision |
| `/rule/[hts]` | One Chapter 99 provision's own page: full legal scope (ancestor text included, not just its own row), its rates, what it references/excludes/is excluded by, and the notes it cites |

## What's precomputed, and why

`hts_coverage` (a materialized view in `db/schema.sql`) answers "which base
codes have any Chapter 99 exposure, and roughly how much" -- the question
`/` and every search ask, over all 23k+ base codes. The single-code deep
query on `/hts/[code]` stays a live, indexed lookup; it's already cheap.
`workflows/parser.py`'s `finalize` task refreshes the view after every load
commits, so it's never stale relative to what Part 2 just parsed. Two
`pg_trgm` GIN indexes (on `hts_base.description` and `rule.context_text`)
back the fuzzy search, same "compute once" idea applied to an index instead
of a view.

**Citation-precision-aware matching, not exact equality.** A Chapter 99
provision can cite a base code at 8-digit precision (`"0402.29.50"`) while
the actual `hts_base` row is stored 10-digit (`"0402.29.50.00"` -- a real,
common shape in the source data, not every subheading has its own bare
8-digit row). Every query here matches `target_hts = code OR code LIKE
target_hts || '.%'`, not bare equality -- exact-match alone silently misses
most real matches (see the audit in `SUBMISSION.md`).

**Every lookup query is cached** (`unstable_cache`, 1-day revalidate, in
`lib/queries.ts`) -- the breadcrumb, applicable-rules table, a rule's own
detail/references/notes, and the landing-page examples. A repeat visit to a
code or rule never touches Postgres until the cache entry ages out.
Verified directly: warm a page, stop the `db` container, request it again --
still 200 with real data, while an unvisited code correctly 500s. Search
(`searchHtsBase`) is deliberately left uncached -- free-text queries have far
higher cardinality than the bounded set of codes/rules people actually
revisit, so caching every distinct typed string would mostly grow the cache
for one-off lookups rather than cut real repeat work; it's already fast via
the `pg_trgm` indexes either way. One tradeoff worth knowing: after a fresh
parser run, a previously-cached code/rule page can serve up to a day of
stale data before picking up the change -- there's no invalidation hook tying
the app to parser runs (a `revalidateTag` API route the parser calls after
`finalize` would close that gap, not built here).

## What this deliberately doesn't do

- **No stacking-order resolution.** When several provisions apply to one
  code, the page lists all of them plus their exclusion relationships to
  each other -- it does not claim to know which one governs a given entry.
  That needs CBP's CSMS filing instructions, which the HTSUS itself never
  states and this dataset doesn't include.
- **No currently-active/expired flag.** Some listed provisions are long
  expired (a subchapter can carry a compiler's note saying so), and there's
  no structured, row-level signal for that in the parsed data. Said plainly
  on the page, not hidden.
- **No LLM-backed search.** Trigram fuzzy matching over descriptions is
  enough for this scope.

## Structure

```
lib/db.ts        Postgres client (`postgres` package, no ORM)
lib/queries.ts    Typed query functions -- the only place SQL lives
lib/format.ts     Renders a (rate_kind, rate_value, rate_text) triple as text
components/RuleTable.tsx   Client component: the sortable/filterable table
app/page.tsx                 Search / landing
app/hts/[code]/page.tsx       The core lookup page
app/rule/[hts]/page.tsx       Single-provision detail page
```
