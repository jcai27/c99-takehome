#!/usr/bin/env bash
#
# Apply db/schema.sql to the chp99 database.
#
#   ./setup.sh                 apply db/schema.sql
#   ./setup.sh path/to.sql     apply something else
#
# Safe to run twice: the schema drops what it creates before creating it. That
# also means it wipes parsed data — it is a schema reset, not a migration.
#
# Needs the stack up (./dev.sh). Runs psql inside the db container, so you don't
# need a local postgres client.

set -euo pipefail

cd "$(dirname "$0")"

SCHEMA="${1:-db/schema.sql}"

if [ ! -f "$SCHEMA" ]; then
  echo "no such file: $SCHEMA" >&2
  exit 1
fi

if [ -z "$(docker compose ps -q db 2>/dev/null)" ]; then
  echo "the db container isn't running — start the stack first:" >&2
  echo "  ./dev.sh" >&2
  exit 1
fi

# ON_ERROR_STOP so a failure exits non-zero instead of scrolling past.
docker compose exec -T db \
  psql -U postgres -d chp99 -v ON_ERROR_STOP=1 -q < "$SCHEMA"

echo "applied $SCHEMA"
docker compose exec -T db psql -U postgres -d chp99 -c '\dt'
