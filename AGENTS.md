# Chapter 99 take-home

## Infrastructure: use the compose stack

Everything runs from `docker-compose.yaml` at the repo root. **Do not start a
Hatchet worker directly on the host** — run it through the `worker` profile so it
gets the right connection settings, dependencies, and network.

```bash
./dev.sh        # everything, with hot reload — Ctrl-C to stop
./setup.sh      # apply db/schema.sql to the chp99 database
./cleanup.sh    # remove every container, volume and network for the project
```

`dev.sh` brings up Postgres, Hatchet, the worker and the app, then watches
`workflows/`. `setup.sh` applies the schema — rerunnable, but it drops and
recreates, so it wipes parsed rows. `cleanup.sh` puts you back to an empty
database, so the next `./dev.sh` starts as a fresh clone would.

The plain compose commands work too. The worker and app are opt-in profiles and
do not start with a bare `up`:

```bash
docker compose up -d                     # just Postgres and Hatchet
docker compose ps                        # db, hatchet, hatchet_db -> (healthy)
docker compose --profile worker watch    # the worker, with hot reload
docker compose --profile app up -d       # the Part 3 app
```

Hatchet runs its migrations on first boot; all three services report healthy in
under a minute. Wait for `hatchet` to be healthy before starting a worker
against it.

### Services and ports

| Service | Host | In-container | What it is |
| --- | --- | --- | --- |
| `db` | `localhost:5432` | `db:5432` | Postgres 16. Your application database, `chp99` |
| `hatchet` | `localhost:8080` (UI/API), `localhost:7077` (gRPC) | `hatchet:7077` | Hatchet Lite. No login — auth is compiled out, and worker credentials are already in `workflows/.env` |
| `hatchet_db` | — | `hatchet_db:5432` | Hatchet's own database. Don't put your data here |
| `worker` | — | — | Profile `worker`. Runs the Hatchet worker |
| `app` | `localhost:3000` | — | Profile `app`. The Part 3 server |

Stock ports, so stop anything already on 5432/8080/3000 first. To remap, use a
`docker-compose.override.yaml` — but leave gRPC on `7077`, which both the worker
token and Hatchet's own internal dial assume. Compose _appends_ port lists on
merge, so you'll want `ports: !override [...]` to replace rather than add.

From inside a container the database is `db:5432`, not `localhost:5432`. Both
`worker` and `app` read `DATABASE_URL` from the environment for this reason.

`data/` holds downloads and cached payloads. It's gitignored, so nothing you put
there ends up in your submission.

### Running the worker

`./dev.sh` — or `docker compose --profile worker watch` for the worker alone.

Either runs in the foreground and streams logs, replacing `up -d` plus
`logs -f`. Editing any `.py` under `workflows/` restarts the worker
automatically — which matters because **Python caches imported modules**, so a
worker left running after an edit keeps serving the old code and the run
succeeds with stale results, with no error to tell you. Changing
`pyproject.toml` also restarts, picking up the new dependency via `uv sync`.

If you would rather run it detached, `docker compose --profile worker up -d`
works and ignores the watch config — but then restart it yourself after every
workflow edit.

**Register new workflows in `workflows/worker.py`.** If you forget, the engine
accepts the run and it sits queued forever with nothing to pick it up.

### Common operations

```bash
docker compose logs -f worker                 # worker output
docker compose exec -T db psql -U postgres -d chp99    # a psql shell
docker compose restart worker                 # after a change, if not using watch
docker compose down                           # stop everything, keep the data
./cleanup.sh                                  # ...and drop every volume
```

Before wiping volumes, stop any host-side worker first. An orphaned one keeps
reconnecting against registrations the fresh Hatchet has never seen and floods
its log with `could not get worker <uuid>`. Check with
`lsof -nP -iTCP:7077 | grep -v com.docke` — it should show nothing.

### The Hatchet CLI

The dashboard is fine for watching a run; the CLI is faster for inspecting a
failed one. Two things about this repo the skill references below don't know:

```bash
export HATCHET_CLIENT_SERVER_URL=http://localhost:8080
hatchet profile add --name chp99 \
  --token "$(grep '^HATCHET_CLIENT_TOKEN=' workflows/.env | cut -d= -f2-)"

hatchet runs list -p chp99 --since 1h -o json
```

**Don't ask for a token** — it's in `workflows/.env`, committed on purpose. The
dev image has auth compiled out and ships one fixed non-expiring token, so it
isn't a secret.

**Keep `HATCHET_CLIENT_SERVER_URL` exported for every command**, not just the
first. The token names the container-internal `8888` in its `aud`, `iss` and
`server_url`, and `hatchet profile add` has no `--address` flag — so the profile
stores `8888` and every request 403s without the override.

<!-- hatchet-skills:start -->
## Hatchet Agent Skills

Hatchet agent skills are installed in `skills/hatchet-cli/`. When working with this project's Hatchet workflows, read the relevant reference:

- **Setup CLI**: `skills/hatchet-cli/references/setup-cli.md`
- **Start worker**: `skills/hatchet-cli/references/start-worker.md`
- **Trigger & watch**: `skills/hatchet-cli/references/trigger-and-watch.md`
- **Debug a run**: `skills/hatchet-cli/references/debug-run.md`
- **Replay a run**: `skills/hatchet-cli/references/replay-run.md`

Full skill: `skills/hatchet-cli/SKILL.md`
<!-- hatchet-skills:end -->
