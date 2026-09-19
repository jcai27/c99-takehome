# Part 2 — Parser

A second Hatchet workflow, downstream of the scraper: it reads the raw payloads
[Part 1](PART1_SCRAPER.md) landed and structures them into Postgres.

Keep it separate from the scraper. It should be runnable against payloads that
were fetched an hour ago, without touching the network.

---

## Requirements

The tables below say _what_ has to be in your schema. These are the rules that
apply across all of them:

- **Extract the cross-references to base HTS codes.**
- **Resolve the cross-references.** A Chapter 99 line should be able to reach the
  MFN rate it modifies.
- **Model the notes and connect them to the headings that cite them.** A heading
  citing "U.S. note 2(a) to this subchapter" should get a user to that note's text.
- **Rates must be computable, not just displayable.**

---

## Required tables

Three tables, with these columns at minimum. They're in
[`db/schema.sql`](../db/schema.sql), which you apply with:

```bash
./setup.sh        # needs the stack up — ./dev.sh
```

The file drops what it creates before creating it, so running it twice is safe.
That also means it wipes parsed rows: it's a schema reset, not a migration.

```sql
CREATE TABLE hts_base (
  hts          text PRIMARY KEY,
  description  text,
  mfn_rate_pct numeric
);

CREATE TABLE rule (
  hts         text PRIMARY KEY,
  subchapter  text NOT NULL,
  description text NOT NULL,
  rate_kind   text NOT NULL
    CHECK (rate_kind IN ('free','additive','ad_valorem','no_change','specific','other')),
  rate_value  numeric,
  note_ref    text
);

CREATE TABLE rule_edge (
  source_hts text NOT NULL REFERENCES rule(hts),
  edge_type  text NOT NULL CHECK (edge_type IN ('references','excludes')),
  target_hts text NOT NULL,
  PRIMARY KEY (source_hts, edge_type, target_hts)
);
```

`rule` holds Chapter 99 provisions, `hts_base` holds chapters 1–97, and
`rule_edge` carries the two relationships Chapter 99 states in prose:
`references`, where a provision names the base codes it modifies, and `excludes`,
where a provision carves out other Chapter 99 provisions.

**This is a floor, not a ceiling.** Edit `db/schema.sql` — add columns, add
tables, change what's there. The schema is most of what we're assessing in this
part, and the starting one is deliberately too thin for the domain. Keep it as
the single command that builds your schema from empty, so we can run it.

---

Next: [Part 3 — Full stack app](PART3_APP.md)
