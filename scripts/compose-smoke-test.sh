#!/usr/bin/env bash
# Build the container images and verify the Compose deployment end to end.
#
# The run uses a separate Compose project so it does not touch a real local
# deployment. Its named volume is removed on exit. Set CHORE_TRACKER_HTTP_PORT
# if port 8080 is already in use.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ -n "${DOCKER_COMPOSE:-}" ]]; then
  read -r -a compose <<< "${DOCKER_COMPOSE}"
else
  compose=(docker compose)
fi

export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-chore-tracker-smoke}"
http_port="${CHORE_TRACKER_HTTP_PORT:-8080}"
base_url="http://127.0.0.1:${http_port}"

cleanup() {
  local status=$?
  trap - EXIT
  if (( status != 0 )); then
    echo "--- compose status ---" >&2
    "${compose[@]}" ps >&2 || true
    echo "--- compose logs ---" >&2
    "${compose[@]}" logs --no-color --tail=200 >&2 || true
  fi
  "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  exit "${status}"
}
trap cleanup EXIT

echo "Building and starting the Compose deployment"
"${compose[@]}" up --detach --build --wait --wait-timeout 240

echo "Checking liveness, readiness, frontend, and API proxy"
curl --fail --silent --show-error "${base_url}/health/live" | grep -q '"status":"ok"'
curl --fail --silent --show-error "${base_url}/health/ready" | grep -q '"status":"ok"'
curl --fail --silent --show-error "${base_url}/healthz" | grep -q '^ok$'
curl --fail --silent --show-error "${base_url}/" | grep -q 'id="root"'
curl --fail --silent --show-error "${base_url}/api/family-members/active" | grep -q '^\[\]$'

echo "Checking that the application containers run without root"
backend_uid="$("${compose[@]}" exec -T backend id -u | tr -d '[:space:]')"
frontend_uid="$("${compose[@]}" exec -T frontend id -u | tr -d '[:space:]')"
[[ "${backend_uid}" == "10001" ]] || {
  echo "backend runs as unexpected uid ${backend_uid}" >&2
  exit 1
}
[[ "${frontend_uid}" != "0" ]] || {
  echo "frontend runs as root" >&2
  exit 1
}

echo "Writing a sentinel to the persistent volume"
"${compose[@]}" exec -T backend python - <<'PY'
import sqlite3

with sqlite3.connect("/data/chore-tracker.db") as connection:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS compose_smoke_test ("
        "id INTEGER PRIMARY KEY, note TEXT NOT NULL)"
    )
    connection.execute("DELETE FROM compose_smoke_test")
    connection.execute(
        "INSERT INTO compose_smoke_test (note) VALUES ('persisted')"
    )
PY

echo "Stopping and starting again without removing the volume"
"${compose[@]}" down
"${compose[@]}" up --detach --wait --wait-timeout 240

"${compose[@]}" exec -T backend python - <<'PY'
import sqlite3

with sqlite3.connect("/data/chore-tracker.db") as connection:
    row = connection.execute("SELECT note FROM compose_smoke_test").fetchone()
assert row == ("persisted",), row
PY

echo "Compose smoke test passed"
