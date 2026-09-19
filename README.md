# Pax AI — Engineering Take-Home

This exercise is drawn directly from the kind of work we do at
[Pax AI](https://paxai.com): pulling messy government trade data into a structured
shape, then building something useful on top of it.

Welcome to the [Pax AI](https://paxai.com) takehome project! We are looking for
curious and motivated engineers to join our team. This exercise is a reflection of
the work we do here: pulling in commplex and messy data, forming into structured
shapes, then building something useful on top.

---

## Background: what is Chapter 99?

The Harmonized Tariff Schedule of the United States (HTSUS) classifies every
imported good under a 10-digit code. Chapter 1 through 97 are the "real"
classifications — `8471.30.01` is a laptop, `0901.21.00` is roasted coffee.

**Chapter 99 is different.** It doesn't classify goods; it _modifies_ the treatment
of goods already classified elsewhere. It's where temporary trade actions live:

- **Subchapter II (9902.xx.xx)** — temporary duty _reductions_. Congress suspends
  the duty on some narrow input good for a few years.
- **Subchapter III (9903.xx.xx)** — temporary duty _increases_. This is where
  Section 301 (China), Section 232 (steel/aluminum), and IEEPA actions live.

The critical structural fact: a Chapter 99 line points _back_ at ordinary HTS
codes, usually in prose inside its own description.

```
9902.04.06  "3,4-Diaminobenzoic acid (CAS No. 619-05-6)
             (provided for in subheading 2922.49.30)"          → Free
```

That parenthetical is the join key. It says: _if your good classifies under
2922.49.30 and matches this description, you may claim this line instead._

Subchapter III works the same way but keys on **country of origin** rather than
product, and layers on exclusions:

```
9903.01.01  "Except for products described in headings 9903.01.02, 9903.01.03,
             9903.01.04 and 9903.01.05, articles the product of Mexico, as
             provided for in U.S. note 2(a) to this subchapter"
            → "The duty provided in the applicable subheading + 25%"
```

Three things to notice, because they drive most of the design work:

1. The rate is not a number. It's _additive to whatever the base rate was_.
2. The line excludes four other lines. Exclusions form a graph, not a list.
3. The chapter notes carry details on how the duties are applied.

You do not need prior customs knowledge. Everything you need is above or in the
source documents. If you find yourself unsure whether a domain interpretation is
right, **write down your assumption and move on**.

---

## What we're assessing

| Area                    | What we're looking for                                                            |
| ----------------------- | --------------------------------------------------------------------------------- |
| **Distributed systems** | Orchestration that survives partial failure. Idempotent, resumable, observable.   |
| **Data extraction**     | Getting structure out of semi-structured sources — prose, PDFs, flattened exports |
| **Data modeling**       | A schema that reflects the domain's real structure                                |
| **Full stack**          | A working, honest UI over your data with sane API design.                         |

---

## The three parts

Each part has its own file. Read them in order — Part 1 also carries the data
source details you'll need throughout.

|                                                |                                                                |                                                |
| ---------------------------------------------- | -------------------------------------------------------------- | ---------------------------------------------- |
| **[Part 1 — Scraper](parts/PART1_SCRAPER.md)** | Fetch the three sources with Hatchet and land the raw payloads | idempotency, failure handling, provenance      |
| **[Part 2 — Parser](parts/PART2_PARSER.md)**   | A second workflow, downstream: structure them into Postgres    | the schema, and whether it reflects the domain |
| **[Part 3 — App](parts/PART3_APP.md)**         | Build something that explains Chapter 99                       | open-ended; your judgment about what matters   |

**Each part has to be runnable on its own.** From a fresh clone and an empty
database, we should be able to create your schema, run the scraper, run the
parser, and start the app — each as a separate command, in that order, without
editing code or hand-applying SQL. Put the commands in `SUBMISSION.md` — the file
is in the repo with the headings already stubbed out; fill them in as you go.
We'll follow them literally.

Running a part twice in a row should be safe.

---

## Scope & Prioritization

- **Part 1 — Scraper.** All three sources, idempotent, with raw payloads persisted.
- **Part 2 — Parser.** Subchapters I, II, and III — headings, hierarchy, notes,
  `provided for in` cross-references, and rate categorization.
- **Part 3 — App.** Something that teaches us how to understand and navigate
  Chapter 99, with a working citation trail back to the source.

This is a complex domain and there is always more to build. Deciding when to stop
is part of the exercise — **stop, and write up what you'd do next**.

---

## What we provide

A `docker-compose.yaml` with Postgres, Hatchet Lite for orchestration, a bare
scaffold for Part 3 in `app/`, and a starter workflow in `workflows/` so you can
confirm the plumbing before writing the scraper. Two commands:

```bash
./dev.sh        # everything, with hot reload — Ctrl-C to stop
./setup.sh      # apply db/schema.sql to the chp99 database
./cleanup.sh    # tear it all down, back to an empty database
```

**[`AGENTS.md`](AGENTS.md) has the details** — services, ports, how to run the
worker, and the gotchas worth knowing before you hit them. It's written for a
coding agent, and it's the same reference if you're reading it yourself.

**Ground rules on the stack**

- **Python or full-stack TypeScript are both good choices** — pick whichever you're
  faster in. We use both, and Hatchet has a well-supported SDK for each. If you'd
  rather use something else entirely, that's fine too; just tell us why.
- Frontend framework is your call. We use NextJS/TypeScript, but we're evaluating
  your judgment, not your framework loyalty.
- Any libraries you want. Don't hand-roll an HTTP client to prove a point. ORMs are
  helpful but not required.
- Hatchet is required for Parts 1 and 2 — the scraper and the parser are both
  workflows. It's how we run everything in production, and orchestration is a
  thing we're specifically assessing. It's a rich framework with lots of functionality
  for building out distributed workflows.

---

## Using AI tools

AI use is encouraged. This repo is designed for use with popular agent harnesses. You should be able to articulate and defend design decisions and technical trade offs.

---

## What to submit

A git repo (or tarball) containing your code, plus a `SUBMISSION.md` covering:

1. **How to run it.** The command for each part, in order, from a fresh clone and
   an empty database.
2. **Your data model**, and why. This is the section we read most carefully — walk
   us through how you decided to represent Chapter 99's relationship to the rest
   of the schedule.
3. **What you built for Part 3, and why that.** What you decided was worth
   understanding about this data, what you left out, and how your storage layer is
   shaped to serve it.
4. **What you'd do with another week.** Known bugs, shortcuts, the thing that's
   held together with tape. Be blunt; we're all engineers here.
5. **Assumptions you made** where the data was ambiguous.
6. **Where you used AI tools**, and anything you shipped without fully verifying.

Your project should be runnable from a clean-clone.

---

## Questions

Email **aaron@paxai.com**.

Good luck. We're looking forward to seeing what you build.
