# Submission

<!--
Fill this in as you go, not at the end. The headings below are the six things
the README asks for; delete this comment and write under each one.
-->

## 1. How to run it

<!--
The command for each part, in order, from a fresh clone and an empty database.
We will follow these literally, so include the setup steps you'd otherwise do
from memory. Say what we should see when each one works.
-->

### Part 1 — Scraper

```bash
./dev.sh                                   # from repo root; brings up db, hatchet, worker, app
cd workflows && uv sync
uv run python -m scraper_run
```

What you should see: the current HTS revision (e.g. `revision=2026HTSRev19`),
then one line per source (`chapter99`, `base_schedule`, `notes_pdf`) showing
`fetched` or `cached`, its size, and a sha256 prefix. On disk:

```
data/latest.json                       # points at the newest complete run
data/runs/<revision>/chapter99.json
data/runs/<revision>/base_schedule.json
data/runs/<revision>/chapter99_notes.pdf
data/runs/<revision>/*.meta.json       # per-source fetch provenance
data/runs/<revision>/manifest.json     # revision + all three sources' provenance, combined
```

Safe to run repeatedly: a source already on disk (payload + its `.meta.json`
sidecar both present) is skipped rather than re-fetched. `manifest.json` /
`data/latest.json` are only (re)written once all three sources for that run
have succeeded, so a partial failure can't advance "latest" or look complete.
Verified by hand: killing one source mid-run leaves the other two on disk and
`data/latest.json` untouched; rerunning afterward heals it (re-fetches only
the missing/failed source, reuses the rest, then completes the manifest).

Unit tests for the download/cache/validate/atomic-write mechanism
(`workflows/lib/fetch.py`) — no Docker or network needed:

```bash
cd workflows && uv run pytest
```

### Part 2 — Parser

```bash
./setup.sh                     # apply db/schema.sql — needs ./dev.sh up
cd workflows && uv sync
uv run python -m parser_run    # needs a completed scraper run; touches no network
```

What you should see: a row-count summary per table, e.g.

```
revision=2026HTSRev19
hts_base           26246 rows
rule                3111 rows
note                  99 rows
rule_edge           9361 references, 1584 excludes
rule_note_ref       3820 links
```

Safe to run repeatedly (each table is reloaded inside its own transaction —
`TRUNCATE` then bulk insert, so a rerun reproduces identical counts, verified
by hand) and safe to run against a freshly-reset schema (`./setup.sh` then
`parser_run` again, also verified).

Unit tests for the two purest, highest-risk-of-silent-bugs pieces — rate
categorization and hierarchy resolution — no Docker or Postgres needed:

```bash
cd workflows && uv run pytest tests/test_rates.py tests/test_hierarchy.py
```

### Data-quality audit (Part 2, after building)

Before building Part 3 on top of Part 2's output, I went back and audited it
end to end with read-only queries against the live tables — beyond what I'd
spot-checked while building — and found two real extraction bugs, both fixed
and reverified:

- **`references` edges leaking Chapter-99-internal citations**: 230 of 9,591
  edges (2.4%) pointed at a `99xx` code instead of a base-schedule one, because
  `"provided for in heading(s) X"` also appears in Chapter 99's own
  self-referencing prose (e.g. `9903.01.25`: "...except **as provided for in
  headings** 9903.01.34 and 9903.02.01..."). Fixed by filtering any extracted
  target starting with `99` out of `references` — by definition it can only
  ever mean a base (chapters 1-97) code.
- **A whole exclusion phrasing was never matched**: `"except as provided for
  in headings X"` is a second, real exclusion pattern (123 occurrences in the
  raw data) alongside the one already handled (`"except for products
  described in headings X"`, 191 occurrences) — my extractor only recognized
  the second. Fixed by extending the trigger regex to catch both. Net effect
  on `9903.01.25` specifically: went from 0 `excludes` edges to the correct
  102.
- Confirmed clean and untouched: hierarchy/rate resolution (`hts_base`
  coverage still exactly 23,193 resolved / 3,053 correctly-NULL group rows)
  and note-ref linking (zero `rule.note_ref` summaries without a matching
  `rule_note_ref` row).
- One non-bug worth noting since it affects how Part 3 queries this data:
  citation precision varies. A rule can cite a base code at 8-digit precision
  (`"0402.29.50"`) while the actual `hts_base` row is stored 10-digit
  (`"0402.29.50.00"`, a common real shape — not every subheading has a
  standalone 8-digit row). Matching `rule_edge.target_hts` by exact equality
  alone silently misses most real matches (13% resolved); matching "exact, or
  a dot-prefix of the stored code" resolves 98.4%. Part 3's queries use the
  latter.

### Final audit (after Part 3, before shipping)

A second, fresh pass across all three parts, specifically hunting for
anything still missed — beyond what the audit above already caught. Two more
real, confirmed bugs, both fixed and reverified:

- **The parser was silently dropping a real rate for 511 rule rows.** The
  source JSON has a fourth rate-bearing field, `additionalDuties`
  (`"66.6¢/kg"`), used instead of `general` for certain provisions — mostly
  subchapter IV's Section 22 quota price-bracket ladders (`"Valued less than
  25¢/kg"`, etc.). I was only ever reading `general`, so these rows showed
  "not stated" in the app despite a real, specific rate sitting right there
  in the data. Fixed with a fallback in `load_rules`
  (`categorize(general) or categorize(additionalDuties)`); `rate_kind =
  'specific'` went from 3 rows to 460 after the fix. (`quotaQuantity` and the
  misspelled `addiitionalDuties` field are always empty in the real data —
  confirmed, not just assumed — so nothing else is being silently dropped
  there.)
- **A PDF text-extraction false positive was swallowing two real notes.**
  The boilerplate phrase "...in lieu of the rate provided in chapters 1
  through 97." happened to line-wrap so `"97."` landed at the start of a
  line — indistinguishable from a real note boundary by the
  monotonically-increasing heuristic alone (97 > 1, so it was accepted,
  eating subchapter XX's real notes 2 and 3 into its body). Fixed by
  rejecting any candidate immediately preceded by "through" — the standard
  English range-connector, and exactly what precedes every instance of this
  pattern in the source. Verified: subchapter XX now correctly shows notes
  1, 2, 3; overall note-citation resolution went from 65/67 to 66/67.

**Documented, not fixed** (real, but lower priority than what's above):
- `hts_base` doesn't capture `special`/`other` preferential-program text at
  all (7,099 and 11,415 real rows have it) — asymmetric with `rule`, which
  does. Lower priority since it's base-schedule FTA eligibility, not the
  Chapter 99 story this app tells.
- `units` (unit of quantity, e.g. "kg", "No.") is populated on ~76% of base
  rows and entirely unused.
- One remaining unresolved note citation is a **source-document**
  inconsistency, not ours: a footnote on `9903.88.16` cites "note 20 to this
  chapter," almost certainly meaning subchapter III's own note 20 (which
  exists, and is about the same tariff family), but literally says
  "chapter." Left unresolved rather than guessed at.
- `code`/search query values flow into SQL `LIKE` patterns unescaped, so a
  literal `%` or `_` in the input acts as a wildcard. Not a security issue
  (fully parameterized, no injection possible) — just a correctness quirk on
  deliberately unusual input, e.g. a URL someone hand-edits.

### Part 3 — App

```bash
cd app && npm install && npm run dev    # -> http://localhost:3000
```

Needs a database that's already been through Parts 1 and 2. What you should
see: a search box and a grid of example codes with real Chapter 99 activity
(e.g. `1806.32.80.00`, 163 provisions); searching or clicking through to
`/hts/<code>` shows the code's resolved base rate plus a sortable/filterable
table of every applicable Chapter 99 provision; clicking a rule code goes to
`/rule/<hts>` for its full legal scope, rates, reference/exclusion graph, and
cited notes. Verified against the exact README Mexico example end-to-end:
`/rule/9903.01.02` correctly shows "Excluded by: 9903.01.01."

## 2. The data model, and why

<!--
The section we read most carefully. Walk us through how you decided to
represent Chapter 99's relationship to the rest of the schedule.
-->

I designed this from the real fetched data, not the README's simplified
examples — `db/schema.sql` has the full schema and inline reasoning; this is
the summary of *why* each addition over the starter schema exists, each
backed by something I found by actually reading `data/runs/*/chapter99.json`,
`base_schedule.json`, and the notes PDF before writing any parsing code.

**Both source JSON exports are flat lists encoding a hierarchy, not flat
tables.** An `indent` field (and a `superior` flag on headerless rows) hides
real structure: a heading (`"0101"`) or subheading (`"0101.90"`) is its own
row with no rate; a 10-digit statistical suffix (`"0101.21.00.10"`, "Males")
carries no rate of its own either — it inherits its 8-digit legal ancestor's
rate. **56% of `hts_base` leaf rows fall into this second case.** Taking the
starter schema literally (`hts_base(hts, description, mfn_rate_pct)`, no
hierarchy) would leave the majority of rows' rates NULL even though the rate
is knowable. So `hts_base` and `rule` both got `parent_hts` + `indent`, and
the parser walks the hierarchy to resolve an effective rate for every row
that has one, marking `rate_inherited` so the provenance of that number isn't
lost. Verified: `0101.21.00.10` correctly shows `rate_inherited=true` with
`0101.21.00`'s `Free`.

**Chapter 99 exclusion clauses can live on an ancestor row, not the rule's
own text.** `9903.01.13` ("Crude oil, natural gas...") is a child of a
*headerless* row (no htsno of its own) whose text is "Except for products
described in headings 9903.01.11, 9903.01.12, 9903.01.14 and 9903.01.15,
articles the product of Canada:". Extracting exclusions from each row's own
`description` alone would silently miss this — a real edge, not a contrived
one. `rule.context_text` is the ancestor-chain text concatenated with the
row's own text, in document order; reference/exclusion extraction runs
against that, not `description`.

**Subchapter membership is derived arithmetically, not hardcoded.** The live
data already has heading prefixes (`9901, 9902, 9903, 9904, 9908, 9915,
9917–9922`) well beyond the README's `9902`/`9903` example. I cross-checked
every one against the PDF's own `SUBCHAPTER <roman numeral>` page headers —
perfect 1:1 correspondence, heading `99XX` is always subchapter `XX`. A
hardcoded table would already be stale; the arithmetic derivation
(`lib/refs.py:subchapter_of`) isn't.

**The notes PDF is mined only for note prose, detected by page-header
vocabulary, not content.** The same PDF also contains the tariff table
re-rendered as jumbled multi-column text — never used as a data source (the
JSON already has it reliably). My first cut detected "the table has started"
by content pattern (a jammed heading-number shape), and it broke on real
data: Subchapter III's notes legitimately contain a 400+ line embedded list
of excluded base HTS codes that's indistinguishable from a table row by
content alone. Fixed to detect the table by its column-header vocabulary
("Rates of Duty", "Article Description", "Heading/", "Subheading" clustered
together) instead. Note numbering resets per `(scope, note_type)` — subchapter
II's "note 2" is unrelated to subchapter III's "note 2" — so `note`'s natural
key is the triple, not a bare number.

**A rule can cite more than one note**, confirmed by a real record citing
both a statistical note and a different subchapter's U.S. note at once. A
single `note_ref text` column (kept, per the required-minimum columns) can't
hold that, so `rule_note_ref` is a proper many-to-many table underneath it —
`note_ref` stays as a human-readable summary, `rule_note_ref` is what a query
actually joins against.

**Rates are categorized, not just stored,** via a small cascade
(`lib/rates.py`) — `free` / `ad_valorem` / `additive` / `no_change` /
`specific` / `other`, with the raw source text always kept alongside so an
imperfect categorization never loses information. `additive` exists because
"The duty provided in the applicable subheading + 25%" is a modifier on a
rate this table doesn't hold, which a single numeric column can't express —
this is the starter schema's own framing, and testing against real data
confirmed it's necessary (244 rule rows are `additive`). `special_text` and
`other_text` on `rule` keep the preferential/FTA and column-2 rate text the
source carries (`special`/`other` columns) rather than silently dropping them
in favor of the single `general`-derived `rate_kind`.

Everything above is additive to the floor schema — every required-minimum
column is still there, verbatim, on every table.

## 3. Part 3: what you built, and why that

<!--
What you decided was worth understanding about this data, what you left out,
and how your storage layer is shaped to serve it.
-->

**What I built**: a narrow, deep lookup, not a browse-everything catalog —
we discussed the alternative (a broad catalog/dashboard) and agreed this was
the better product for actually teaching the domain. Pick a base HTS code
and get a sorted, filterable list of every Chapter 99 provision that applies
to it: resolved rate, whether another provision excludes it, and its notes,
one click away from the full legal text and the exclusion graph around it.
Next.js (App Router) + TypeScript, the `postgres` package directly (no ORM).

**Why this and not something broader**: before designing anything I queried
the live data, and two numbers shaped the whole product. Only ~2,582 of
23,193 real base codes (about 11%) have *any* Chapter 99 exposure — most of
the tariff schedule is untouched, so the landing page leads with known-good
examples rather than a search box staring at a mostly-empty dataset. And a
single code can have well over a hundred applicable provisions (`1517.90.60`
has 163 — subchapter IV administers several commodities through
price-bracket tables, each its own heading pointing at the same base code) —
which is exactly why "sorted and filterable" mattered more than "grouped
into a pretty list": at that size, filtering by subchapter/rate kind and
sorting by rate magnitude is what actually makes the page usable, not a
design choice made for its own sake.

**What's precomputed, and why** (the spec's own prompt: what's worth
storing, and how do you keep it true): the per-code deep query is already a
cheap indexed lookup and stays live. What's expensive — asked on every visit
to the search/landing page — is the aggregate question over all 23k+ base
codes at once ("which ones have coverage, and how much"), so that's a
materialized view (`hts_coverage`). Kept true by one `REFRESH MATERIALIZED
VIEW` at the end of the parser's `finalize` task — the same idempotent run
that reloads the base tables also refreshes what's derived from them, so
there's no separate schedule to forget. Two `pg_trgm` GIN indexes back
fuzzy search the same way — an index built once, not recomputed per request.

**Added after the fact: request-level caching**, once it came up in
conversation — every lookup query (`lib/queries.ts`) is wrapped in Next's
`unstable_cache` with a 1-day revalidate, so a repeat visit to a code or
rule never touches Postgres again until the entry ages out. Verified, not
assumed: warmed two pages, stopped the `db` container entirely, re-requested
them — both still returned 200 with real data, while an unvisited code
correctly 500'd. Search stays uncached on purpose (unbounded query
cardinality vs. the bounded set of codes/rules people revisit — see
`app/README.md`). The honest tradeoff: nothing currently ties cache
invalidation to a parser run, so a fix or a new revision can take up to a
day to show up on an already-visited page without an app restart.

**A real bug the app surfaced, caught before shipping**: the obvious query
("`rule_edge.target_hts = this code`") resolved only 13% of real references.
Chapter 99 cites codes at 8-digit precision; a lot of `hts_base` rows only
exist at 10-digit precision with a `.00` statistical suffix and no
standalone 8-digit row. Matching "exact, or a dot-prefix of the stored code"
instead resolves 98%. Every query in `lib/queries.ts` uses the latter —
documented in `app/README.md` since it's easy to regress by writing an
"obviously correct" equality check.

**What I left out, on purpose**:
- *Stacking-order resolution.* When several provisions apply to one code,
  the page shows all of them plus their exclusion relationships — never a
  claim about which one governs a given entry. That needs CBP's CSMS filing
  instructions, which this dataset doesn't have (and which, per
  `PART3_APP.md` itself, the HTSUS never states either).
  A disclaimer says this directly on every result page, rather than
  presenting a flat list that implies more certainty than the data supports.
- *A currently-active/expired flag.* Some listed provisions are long expired
  — an entire subchapter (II) is, per its own compiler's note in the PDF —
  and there's no row-level structured signal for that (Part 2 doesn't parse
  compiler's notes; see Part 2's assumptions). Rather than fake a status
  badge, the page just doesn't claim one.
- *LLM-backed natural-language search.* We discussed this explicitly and
  agreed the product is the structured lookup, not a chat interface —
  trigram fuzzy search over descriptions covers the real need (find a code
  from a product description) without an API dependency, cost, or latency.

## 4. What you'd do with another week

<!--
Known bugs, shortcuts, the thing that's held together with tape. Be blunt.
-->

Blunt, in rough priority order:

- **Compiler's notes aren't parsed** ("the provisions of this subchapter have
  expired..."), so the app can list long-dead provisions with no way to flag
  them as such. This is the single biggest thing standing between "every
  provision on record" and "your actual current duty." I'd model a third
  `note_type` for these and expose an "expired" badge — the pattern is
  bracketed text right after the `SUBCHAPTER` header, and it's a bounded,
  well-understood addition given how `lib/notes_pdf.py` is already shaped.
- **Note-ref regex coverage is good, not exhaustive** — `lib/refs.py`'s
  `_NOTE_PATTERNS` list covers the phrasings I found by grepping the real
  data, not a formal grammar. A rule citing a note in a phrasing I didn't
  see gets no link, silently. Same caveat, smaller stakes, for
  `extract_references`/`extract_exclusions`'s window-based extraction — it's
  validated against real data with real bug fixes, but it's not a parser
  with a guarantee, and a sufficiently unusual sentence could still slip
  past it uncounted rather than wrongly counted (I biased fixes toward "miss
  a real edge" over "invent a fake one" throughout).
- **No tests for `lib/refs.py` or `lib/notes_pdf.py`** — Part 1 and the
  purest Part 2 modules (`rates`, `hierarchy`) have unit tests; the
  regex-heavy extraction modules were validated by running them against the
  full real dataset repeatedly (and that process is exactly what caught
  every bug documented above), but that's validation-by-rerun, not a
  regression suite. I'd turn the real examples already used for validation
  (`9903.01.25`, the Mexico exclusion chain, the ethanol/corn references)
  into `tests/test_refs.py`.
- **The app has no automated tests at all** — every page was verified by
  hand (curl for content, Playwright screenshots for rendering, zero console
  errors) against the live stack, not by a suite that runs on its own.
- **Search is `ILIKE`/trigram, not ranked by relevance** — good enough for
  "find a code from a rough description," but a longer query doesn't
  meaningfully outrank a shorter partial match the way a real search engine
  would.
- **Single revision only, everywhere it matters for display.** `data/runs/`
  keeps every fetched revision, and `import_run` logs every parse, but
  `hts_base`/`rule`/etc. only ever hold the latest one — there's no "what did
  this look like under Rev15" view. Deliberate scope (see the data-model
  section), but worth naming as a real limitation, not an oversight.
- **App cache has no invalidation hook tied to a parser run.** It's a 1-day
  revalidate, so after rerunning the parser, an already-cached page can
  serve last revision's answer for up to a day. A `revalidateTag` API route
  the parser calls after `finalize` would close this — same "keep it true"
  problem the materialized view already solves, just not extended to the
  app's own cache.
- **`hts_base` doesn't carry `special`/`other` preferential-program text**
  (found in the final audit — `rule` has this, `hts_base` doesn't; real data
  on ~7k/~11k rows, just not modeled).
- **URL/search input flows into SQL `LIKE` patterns unescaped**, so a
  literal `%` or `_` acts as a wildcard on deliberately unusual input. Not a
  security issue — fully parameterized, no injection — just a correctness
  quirk worth an `ESCAPE` clause with another pass.

## 5. Assumptions

<!--
Where the data was ambiguous and you had to pick. What you picked, and why.
-->

- **Revision changes mid-exercise, as warned.** The README's snapshot was Rev15
  (2026-08-03); by the time I ran the scraper it was Rev19. Confirmed the
  design handles this: revision is resolved fresh at the start of every
  workflow run (not baked into a constant), and each revision gets its own
  `data/runs/<revision>/` directory, so nothing from an older run is
  overwritten or lost.
- **Part 1 doesn't touch Postgres.** The spec's constraint on Part 2 ("runnable
  against payloads fetched an hour ago, without touching the network")
  implied the scraper's responsibility ends at `data/` — provenance for this
  part lives in `manifest.json` / the `.meta.json` sidecars, not in a
  database table. Part 2 will carry that provenance into Postgres.
- **Payload validation before committing a file.** A 200-status maintenance or
  error page could otherwise be saved as if it were valid data. JSON sources
  must parse and be a non-empty array; the PDF must start with `%PDF-`. This
  wasn't explicitly asked for but seemed necessary for "leave data in a
  coherent state."
- **A note's sub-lettered structure (a/b/i/ii/(A)/(B)) is kept as part of
  that note's full text, not modeled as separate rows.** "U.S. note 2(a)"
  resolves to note 2's complete text rather than a distinct sub-row. Full
  recursive outline modeling would add real parsing fragility for marginal
  navigational benefit over "show the whole note, the citation already said
  which one."
- **Top-level note numbering is treated as monotonically increasing, not
  strictly sequential.** A note's body can contain its own nested numbered
  sub-list (confirmed: this produced a genuine duplicate-key crash against
  real data before the fix), so a candidate match only counts as a new note
  if its number is *greater* than the last accepted one — this also
  correctly tolerates real gaps in the source numbering (subchapter III's
  real notes skip from 3 straight to 5, a repealed/renumbered provision, not
  an extraction bug) without over- or under-splitting. Not pixel-perfect
  against every possible PDF layout quirk, but verified duplicate-free
  against the full real document.
- **Only `general` is categorized into `rate_kind`/`rate_value`.** `special`
  and `other` are kept as raw text columns rather than separately
  categorized — `general` is the column that matters for "what does this
  provision do to the MFN rate," and categorizing three columns identically
  seemed like more schema than the requirement asked for.
- **A blank `general` on a real (non-group) Chapter 99 rule** — e.g. a quota
  provision, where the chapter's own statistical notes explain duty isn't
  expressed as a simple rate for those — is categorized `rate_kind='other'`
  rather than left NULL, since `rule.rate_kind` is a required NOT NULL
  column and `'other'` already means "a real rate exists in a form not
  modeled precisely here," which fits.
- **A code with zero Chapter 99 coverage is a normal, expected result, not
  an error state.** ~89% of base codes have none. The app treats "no Chapter
  99 provision on record" as a clearly-labeled, legitimate answer rather
  than something to apologize for or hide.
- **The "excluded by" flag is informational, not a verdict.** A provision
  being named in another's `excludes` clause is shown as a flag to
  investigate, not as "this provision doesn't apply" — the exclusion clauses
  themselves are often conditional (by date, by country, by sub-value), and
  fully evaluating them is exactly the stacking-order problem this app
  deliberately doesn't claim to solve.

## 6. Where you used AI tools

<!--
Including anything you shipped without fully verifying.
-->

- **Part 1 (scraper)** was built with Claude Code end-to-end: design discussion
  and a written plan before any code, then the workflow/task code, then live
  verification against the real `hts.usitc.gov` endpoints and the actual
  compose stack (not just read-through) — including deliberately breaking one
  source's URL to confirm partial-failure behavior, and rerunning twice to
  confirm caching/idempotency. Nothing here shipped unverified.
- **Part 2 (parser)** likewise: the plan was written only after reading the
  real scraped data and the real notes PDF (not the README's simplified
  examples), and every parsing module (`lib/hierarchy.py`, `lib/rates.py`,
  `lib/refs.py`, `lib/notes_pdf.py`) was validated by running it against the
  full real dataset before being wired into the workflow, which caught
  several real bugs I'd otherwise have shipped silently: 6-digit subheading
  codes (`2207.20`) being dropped by a regex that only matched 10-digit
  ones; a heading-list cap that silently truncated "heading 2710 or 3824" to
  just one code; a table-boundary heuristic that broke on Subchapter III's
  notes (which legitimately contain a 400+ line embedded HTS code list
  indistinguishable from a table by content); two subchapters (XXI, XXII)
  whose notes have no "U.S. Notes" label at all and were being silently
  dropped; a duplicate-key crash from a note's nested numbered sub-list; and
  a `sorted()` crash from comparing `None` against a string. All confirmed
  fixed by rerunning against the live stack afterward, not just by reasoning
  about the code.
- **Before starting Part 3, I went back and audited Parts 1 and 2 end to
  end** at the user's request — read-only data-quality queries against the
  live tables, beyond what had been spot-checked while building. That's what
  found the two `references`/`excludes` extraction bugs and the
  citation-precision issue documented above; both were fixed and reverified
  before any Part 3 code was written, not discovered afterward.
- **Part 3 (app)** followed the same pattern: a plan grounded in real
  queries against the live data (the ~11% coverage figure, the 163-provision
  outlier, the citation-precision fix) before writing any UI code, then
  verification against the real stack — not just `curl` for status codes,
  but Playwright screenshots of the actual rendered pages (checked for
  visual correctness and zero browser console errors), including the exact
  scenario `README.md` uses to teach Chapter 99 (`9903.01.02`, excluded by
  `9903.01.01`) rendering correctly end to end. One real issue this caught:
  the landing page's "example codes" query initially returned six
  near-duplicate results (a single price-bracket family that all shared the
  same rule count and subchapters) — fixed to diversify by subchapter
  combination once the screenshot made it obviously repetitive. `next` was
  also pinned to a version with a known CVE by my own initial package.json
  (15.1.4); caught by `npm audit`, not by me noticing on my own, and bumped
  to a patched version (15.5.25) plus a `postcss` override before shipping.
