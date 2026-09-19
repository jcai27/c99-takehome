# Workflows

Your Hatchet workflows go here.

## Setup

`./dev.sh` from the repo root runs a worker for you, in a container, and restarts
it when you edit a `.py` here. Trigger a run against it from this directory:

```bash
cd workflows && uv sync
uv run python -m scraper_run
uv run python -m parser_run    # after the scraper — reads data/, touches no network
```

To run the worker on your host instead, don't use `./dev.sh` — start just the
infrastructure, then the worker yourself:

```bash
docker compose up -d        # from the repo root; wait for hatchet to be healthy
cd workflows && uv sync
uv run python -m worker     # one terminal: registers workflows, waits for work
uv run python -m scraper_run   # another
```

**Run one worker at a time.** They share the token in `.env`, so a host worker
and the container worker will both register and Hatchet will hand tasks to
whichever it picks — including the one running code you didn't just edit.

Runs show up in the Hatchet UI at http://localhost:8080 — no login, it opens
straight to the dashboard. Workflows can be triggered from the UI or
programatically.

## Tests

`tests/` has unit tests for the pieces worth testing in isolation: `lib/fetch.py`
(the download/cache/validate/atomic-write mechanism, via a mocked HTTP layer)
and, for the parser, `lib/rates.py` (rate categorization) and `lib/hierarchy.py`
(indent-hierarchy resolution). No Docker, Hatchet, network, or Postgres needed:

```bash
uv run pytest
```

## The worker in Docker

`./dev.sh` is the short version. For the worker alone:

```bash
docker compose --profile worker watch    # foreground, restarts on edit
docker compose --profile worker up -d    # detached, no reload
docker compose logs -f worker
```

Either bind-mounts `./workflows`. Under `watch`, editing a `.py` restarts the
worker for you; adding a dependency to `pyproject.toml` restarts it too, picking
up the new package via `uv sync`. Detached, you restart it yourself with
`docker compose restart worker`.

Either path is fine. Host-running gives you a debugger; the container gives you
one less thing to install and the reload for free. Note that from inside the
container your database is `db:5432`, not `localhost:5432` — the service reads
`DATABASE_URL` from the environment for exactly this reason.

## What's here

| File               |                                                                   |
| ------------------ | ------------------------------------------------------------------ |
| `scraper.py`       | Part 1: fetches the three USITC sources into `data/`               |
| `scraper_run.py`   | Triggers a scraper run and prints a summary                        |
| `parser.py`        | Part 2: structures `data/latest.json`'s payloads into Postgres     |
| `parser_run.py`    | Triggers a parser run and prints a row-count summary               |
| `worker.py`        | The worker process. Register your workflows here                   |
| `lib/fetch.py`     | Shared atomic-download-with-validation-and-skip helper (Part 1)     |
| `lib/paths.py`     | `DATA_DIR` resolution                                               |
| `lib/hierarchy.py` | Resolves the indent-encoded parent/child structure in the JSON exports |
| `lib/rates.py`     | Duty-rate prose -> `(rate_kind, rate_value)` categorization          |
| `lib/refs.py`      | Base-code/exclusion/note-citation extraction, subchapter derivation |
| `lib/notes_pdf.py` | Segments the notes PDF into per-scope U.S./Statistical notes        |
| `lib/db.py`        | `DATABASE_URL` connection helper                                    |
| `tests/`           | Unit tests — `uv run pytest`                                        |
| `.env`             | Hatchet connection settings. Committed — see below                  |

## The shape of a workflow

A workflow is a `Hatchet` instance's `.workflow(name=..., input_validator=...)`,
plus one or more `@workflow.task()`-decorated functions. A task can depend on
others via `parents=[...]`, and read a parent's return value with
`ctx.task_output(parent_task)`.

`scraper.py` is a small DAG: an initial task resolves the current HTS
revision, three tasks fan out from it to fetch each source in parallel, and a
final task fans back in once all three have landed to write a manifest. See
that file, and `lib/fetch.py`, for how retries, idempotency, and atomic writes
are handled.

`parser.py` is a second, independent DAG, downstream only of `data/latest.json`
(never the scraper's tasks directly): `load_hts_base`, `load_notes`, and
`load_rules` fan out from `load_manifest`, then `load_rule_edges` and
`load_rule_notes` depend on `load_rules` (plus `load_notes`, for the latter)
to resolve cross-references and note citations. Each load task truncates and
reloads its own table(s) in one DB transaction — idempotent the same way
Part 1's atomic file rename is, just expressed as a transaction instead.

[Hatchet docs](https://docs.hatchet.run/home/setup) is a great resource for
documentation and patterns.

## Notes

**Register your workflows in `worker.py`.** If you forget, the engine will accept
a run and it'll sit queued forever with nothing to pick it up. This is the most
common way to lose ten minutes here.

**The token in `.env` is committed, and that's deliberate.** We run the Hatchet
dev image, which has auth compiled out — no login on the dashboard, and one fixed
non-expiring worker token that's the same on every auth-disabled instance. It
isn't a secret and it survives `./cleanup.sh`, so there's no setup step and
nothing to rotate. Don't copy the pattern into anything real.
