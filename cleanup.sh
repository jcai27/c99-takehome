#!/usr/bin/env bash
#
# Tear the Docker stack back down to a clean install.
#
#   ./cleanup.sh
#
# Removes every container, volume and network belonging to this project, so the
# next `./dev.sh` starts from an empty database exactly as a fresh clone would.
# Nothing outside Docker is touched.
#
# Two things a plain `docker compose down -v` misses:
#
#   1. Profile-gated volumes. `app_node_modules` and `worker_venv` belong to the
#      `app` and `worker` profiles, so a `down -v` that does not name those
#      profiles leaves them behind. Matching on the project label catches every
#      volume regardless of profile.
#
#   2. Containers stranded on a deleted network. If the project network is
#      removed while a container is attached, `down` cannot remove that
#      container -- teardown needs the network -- and every later `up` fails
#      with "network <id> not found". Force-removing them is the way out.

set -euo pipefail

cd "$(dirname "$0")"

PROJECT=chp99-takehome

# Both profiles named, so profile-gated containers are in scope for `down`.
echo "removing containers, volumes and network"
docker compose --profile worker --profile app down --volumes --remove-orphans

# Anything compose could not remove -- typically stranded on a deleted network.
stranded=$(docker ps -aq --filter "label=com.docker.compose.project=$PROJECT" 2>/dev/null || true)
if [ -n "$stranded" ]; then
  echo "force-removing $(echo "$stranded" | wc -l | tr -d ' ') stranded container(s)"
  # shellcheck disable=SC2086
  docker rm -f $stranded >/dev/null
fi

# Volumes by label rather than by name, for the profile reason above.
vols=$(docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT" 2>/dev/null || true)
if [ -n "$vols" ]; then
  echo "removing $(echo "$vols" | wc -l | tr -d ' ') leftover volume(s)"
  # shellcheck disable=SC2086
  docker volume rm $vols >/dev/null
fi

# The network usually goes with `down`; catch it if a stranded container held it.
nets=$(docker network ls -q --filter "label=com.docker.compose.project=$PROJECT" 2>/dev/null || true)
if [ -n "$nets" ]; then
  # shellcheck disable=SC2086
  docker network rm $nets >/dev/null 2>&1 || true
fi

# --- verify ------------------------------------------------------------------
echo
left_c=$(docker ps -aq --filter "label=com.docker.compose.project=$PROJECT" 2>/dev/null | wc -l | tr -d ' ')
left_v=$(docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT" 2>/dev/null | wc -l | tr -d ' ')
left_n=$(docker network ls -q --filter "label=com.docker.compose.project=$PROJECT" 2>/dev/null | wc -l | tr -d ' ')

if [ "$left_c" -eq 0 ] && [ "$left_v" -eq 0 ] && [ "$left_n" -eq 0 ]; then
  echo "clean: no containers, volumes or networks left for $PROJECT"
  echo "next ./dev.sh starts from an empty database -- re-run the schema."
else
  echo "still present: ${left_c} container(s), ${left_v} volume(s), ${left_n} network(s)" >&2
  exit 1
fi
