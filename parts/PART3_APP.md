# Part 3 — Full stack app

Parts 1 and 2 told you what to build. This one doesn't.

**Build a full stack app that helps someone understand Chapter 99.** What that
means is your call. We are building in a complex domain, with experts dedicating
entire careers to understanding the ins and outs of the HTS code. Build something
that explains how tariffs work to a novice.

**Think of yourself as the primary user.** Not a hypothetical importer, not us —
you. What presentation would have made this domain click faster? Where did you have
to hold five things in your head at once because nothing showed them together?
That confusion is your product spec.

**Speed is part of the design.** The data does not change until the next revision.
So you can compute an answer once and store it, instead of making the database work
it out again on every request. Build the tables your screens need: flatten a join,
add a materialized view, precompute the exclusion graph, store a derived column.

The hard part is choosing. What is worth storing, and how do you keep it true when
the tables under it change? Write down what you picked and why in `SUBMISSION.md`.

---

## Getting started

There's a bare scaffold in [`app/`](../app/README.md) — one route, one query, no
framework. It exists so you don't spend your first twenty minutes on connection
strings.

```bash
./dev.sh                  # from the repo root → http://localhost:3000
```

[`AGENTS.md`](../AGENTS.md) has the stack in full — services, ports, and how to
run the app on your host instead of in a container.

Delete it if it's in your way. The only thing we ask is that
`SUBMISSION.md` tells us how to run what you built.

---

## Additional resources

**Where a Chapter 99 line comes from.** A trade action starts as a presidential
proclamation or a USTR notice, gets published in the **Federal Register**, and
lands in the HTSUS as new 9903 headings. **CBP** then tells filers how to actually
enter the goods via a **CSMS** message. So a single duty has three artifacts: the
legal instrument, the tariff line, and the filing instruction. Our dataset only
has the middle one.

| Source                                                                              | What's there                                                                                         | How to read it                                      |
| ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| [**Federal Register**](https://www.federalregister.gov/)                            | The legal instrument — proclamations and USTR notices that create, amend, or terminate 9903 headings | Open JSON API, no key                               |
| [**USITC HTS**](https://hts.usitc.gov/)                                             | The tariff schedule itself, plus revision history and the notes PDFs                                 | Same `reststop` API you're already using            |
| [**CBP CSMS**](https://www.cbp.gov/trade/automated/cargo-systems-messaging-service) | Filing instructions — stacking order, which 9903 code goes on which line, effective dates            | Web archive + email list; no clean API              |
| [**CBP CROSS**](https://rulings.cbp.gov/)                                           | Binding rulings: how CBP classified a specific real product                                          | JSON search API, no key                             |
| [**USITC DataWeb**](https://dataweb.usitc.gov/)                                     | Actual import volumes and duties collected, by HTS code                                              | Free account; API key for bulk                      |
| [**eCFR Title 19**](https://www.ecfr.gov/current/title-19)                          | The customs regulations themselves                                                                   | Open API, no key — XML for text, JSON for structure |

### Programmatic access

The Federal Register API is the most useful of these and needs no key. Filter by
agency and type — a bare `"section 301"` term search returns mostly unrelated
documents, since §301 also numbers a Clean Water Act provision:

```bash
# Recent USTR notices — where Section 301 actions are announced.
# Brackets are percent-encoded because curl treats [] as a glob.
curl -s -A 'your-app/1.0 (you@example.com)' \
  'https://www.federalregister.gov/api/v1/documents.json?per_page=5&order=newest&conditions%5Bagencies%5D%5B%5D=trade-representative-office-of-united-states&conditions%5Btype%5D%5B%5D=NOTICE&fields%5B%5D=title&fields%5B%5D=publication_date&fields%5B%5D=html_url'
```

The HTS API tells you which revision you're looking at.

```bash
curl -s 'https://hts.usitc.gov/reststop/currentRelease'
# → {"name":"2026HTSRev15","title":"Revision 15 (2026)"}   # as of 2026-08-03

# Keyword search across the schedule, same shape as the bulk export
curl -s 'https://hts.usitc.gov/reststop/search?keyword=laptop'
```

CROSS returns a `tariffs` array on every ruling, which makes it joinable to your
data — and those arrays often contain 9903 codes, so a ruling can show you a real
product with its Chapter 99 treatment already attached:

```bash
curl -s 'https://rulings.cbp.gov/api/search?term=laptop%20backpack&pageSize=5'
# → "tariffs": ["4202.92.3120", ..., "9903.88.03"]
```

eCFR serves regulation text as XML, and the table of contents as JSON:

```bash
# Full text of 19 CFR 141 (entry of merchandise) — XML only, .json returns 406
curl -s 'https://www.ecfr.gov/api/versioner/v1/full/2026-01-01/title-19.xml?part=141'

# Structure of Title 19, for finding the part you want
curl -s 'https://www.ecfr.gov/api/versioner/v1/structure/2026-01-01/title-19.json'
```

### By hand

- **Federal Register** — search by agency ("Trade Representative"), or browse
  [presidential documents](https://www.federalregister.gov/presidential-documents/executive-orders)
  for proclamations. Each document links its own RIN and docket.
- **CSMS** — the [archive](https://www.cbp.gov/trade/automated/cargo-systems-messaging-service)
  is paginated and JS-rendered, so it doesn't scrape cleanly; read it in a browser.
  Messages are the fastest way to understand _stacking order_, which the HTSUS
  itself never states.
- **CROSS** — search a product description in plain English. Rulings show the
  reasoning, which is often the only place a classification boundary is explained.
- **regulations.gov** — public comment dockets for pending actions. The API needs
  a [free api.data.gov key](https://api.data.gov/signup/); the web UI doesn't.

---

Back to: [the main README](../README.md)
