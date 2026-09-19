#!/usr/bin/env bash
#
# Start the whole stack with hot reload.
#
#   ./dev.sh
#
# Brings up Postgres, Hatchet, the worker and the app, then watches
# ./workflows for changes. Editing any .py restarts the worker, which is what
# clears Python's module cache -- a worker left running after an edit keeps
# serving the old code and the run succeeds with stale results, with no error
# to tell you.
#
# Why a script: `watch` is a CLI mode, not something the compose file can turn
# on, and the worker and app are opt-in profiles. This is the one command that
# combines them.
#
# Runs in the foreground and streams logs. Ctrl-C stops watching and stops the
# containers.

set -euo pipefail

cd "$(dirname "$0")"

# Ports we publish. Checked up front because the failure is otherwise a wall of
# compose output ending in "address already in use".
#
# Skipped when our own stack is already up: compose recreates those containers
# itself, and the ports it is holding are not a conflict.
if [ -z "$(docker compose ps -q 2>/dev/null)" ]; then
  check_port() {
    if lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; then
      echo "port $1 ($2) is already in use:" >&2
      lsof -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null | tail -n +2 | sed 's/^/  /' >&2
      return 1
    fi
  }

  busy=0
  check_port 5432 postgres || busy=1
  check_port 8080 "hatchet UI" || busy=1
  check_port 7077 "hatchet gRPC" || busy=1
  check_port 3000 app || busy=1

  if [ "$busy" -ne 0 ]; then
    echo >&2
    echo "Stop whatever is holding those ports and try again." >&2
    exit 1
  fi
fi

echo "starting db, hatchet, worker, app -- Ctrl-C to stop"
echo

# --watch implies up. Both profiles, so a plain ./dev.sh is the whole stack.
exec docker compose --profile worker --profile app up --watch
