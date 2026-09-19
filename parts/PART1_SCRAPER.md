# Part 1 — Scraper

Build a Hatchet workflow that fetches three sources and lands them in durable
storage.

Read [the main README](../README.md) first for background on Chapter 99 and what
we're assessing overall.

---

## The data sources

Three fetches, ~25 MB total:

|     | What                                                   | Size   |
| --- | ------------------------------------------------------ | ------ |
| 1   | Chapter 99 — the provisions themselves                 | ~2 MB  |
| 2   | Chapters 1–97 — the base schedule Chapter 99 points at | ~10 MB |
| 3   | The Chapter 99 notes PDF                               | ~14 MB |

**1. The Chapter 99 JSON** (~3,300 rows, ~2 MB)

```
https://hts.usitc.gov/reststop/exportList?from=9900&to=9999&format=JSON&styles=false
```

**2. The base schedule, chapters 1–97** (~31,900 rows, ~10 MB)

```
https://hts.usitc.gov/reststop/exportList?from=0100&to=9799&format=JSON&styles=false
```

**3. The Chapter 99 notes PDF** (~14 MB)

```
https://hts.usitc.gov/reststop/file?release=currentRelease&filename=Chapter%2099
```

This is the official chapter document. It contains the tariff table _and_ the
U.S. Notes / Statistical Notes for the chapter and for each subchapter. The notes
are what give the headings their legal meaning.

---

## Requirements

- Fetch all three: Chapter 99, chapters 1–97, and the notes PDF.
- Persist the **raw, unmodified** payloads to `data/` before any parsing. Parsing is lossy
  and your parser will have bugs; you want to re-parse without re-fetching.
- Record enough provenance to answer "where did this row come from, and when?"
  The HTSUS is revised several times a year, and a revision can land mid-exercise.
  As of **2026-08-03** the live release was **Revision 15 (2026)** — the same string
  appears in the PDF header and in `currentRelease` — but treat that as a snapshot,
  not a constant.

  ```bash
  curl -s 'https://hts.usitc.gov/reststop/currentRelease'
  # → {"name":"2026HTSRev15","description":"2026 HTS Revision 15","title":"Revision 15 (2026)"}
  ```

- Be idempotent. Running it twice should not corrupt anything or duplicate data.
- Handle errors well, a failure should leave the data in a coherent state.
- Handle failure like the network is real: timeouts, retries with backoff, partial
  success.

---

## Getting started

Hatchet is running from the provided compose file, and `workflows/` already has a
worker plus a workflow that takes an input and returns an output:

```bash
./dev.sh                                       # from the repo root
cd workflows && uv run python -m echo_run "hello"
```

Runs appear at http://localhost:8080 — no login. [`AGENTS.md`](../AGENTS.md) has
the stack in full — services, ports, and how to run the worker on your host
instead — and [`workflows/README.md`](../workflows/README.md) covers the
workflow loop itself.

Hatchet is required here and in [Part 2](PART2_PARSER.md), which is a second
workflow reading what this one writes.

---

Next: [Part 2 — Parser](PART2_PARSER.md)
