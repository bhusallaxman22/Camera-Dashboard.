#!/usr/bin/env bash
# Entrypoint for the all-in-one image.
#
#   all (default)          migrate, then run API + worker(s) + watcher + web UI
#   api | web | watcher    run one role
#   worker [queues...]     run one worker (default queues: ingest analysis ai)
#   migrate                apply database migrations and exit
#   healthcheck            container healthcheck for the role that is running
#   <anything else>        exec'd as the app user, e.g. `z6iii python -m app.cli stats`
set -euo pipefail

cd /app
role="${1:-all}"
[ $# -gt 0 ] && shift

PUID="${PUID:-568}"
PGID="${PGID:-568}"
ROLE_FILE=/tmp/z6iii.role

if [ "$role" != "healthcheck" ] && [ "$(id -u)" = "0" ] && [ "$PUID" != "0" ]; then
  # Make generated-data folders writable for the app user, then drop root.
  # Nothing under /photos is ever touched.
  for d in "${DATA_ROOT:-/data}" "${THUMBNAIL_ROOT:-/data/thumbnails}" \
           "${PREVIEW_ROOT:-/data/previews}" "${CACHE_ROOT:-/data/cache}"; do
    mkdir -p "$d"
    if [ "$(stat -c %u:%g "$d")" != "$PUID:$PGID" ]; then
      if [ "$d" = "${DATA_ROOT:-/data}" ]; then chown "$PUID:$PGID" "$d"; else chown -R "$PUID:$PGID" "$d"; fi
    fi
  done
  exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups -- /usr/local/bin/z6iii "$role" "$@"
fi

migrate() {
  python -m app.cli init-dirs
  local attempt
  for attempt in $(seq 1 30); do
    if alembic upgrade head; then
      return 0
    fi
    echo "database not reachable yet (attempt ${attempt}/30), retrying in 2s" >&2
    sleep 2
  done
  echo "giving up: could not run migrations against DATABASE_URL" >&2
  return 1
}

api() {
  # Open SSE streams never finish on their own; cap graceful shutdown so
  # `docker stop` doesn't hang until SIGKILL.
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
    --proxy-headers --forwarded-allow-ips='*' --no-access-log \
    --timeout-graceful-shutdown 5
}

worker() {
  if [ $# -eq 0 ]; then set -- ingest analysis ai; fi
  exec python -m app.workers.run "$@"
}

watcher() {
  exec python -m app.watchers.run
}

web() {
  cd /web
  # Docker sets HOSTNAME to the container id; Next.js binds to it, so override.
  exec env HOSTNAME=0.0.0.0 PORT=3000 node server.js
}

run_all() {
  migrate
  local pids=() code n
  trap 'kill -TERM "${pids[@]}" 2>/dev/null || true' TERM INT
  api & pids+=("$!")
  for n in $(seq 1 "${WORKER_PROCESSES:-1}"); do
    worker & pids+=("$!")
  done
  watcher & pids+=("$!")
  web & pids+=("$!")

  # If any process stops, stop the rest so Docker restarts the container cleanly.
  set +e
  wait -n
  code=$?
  echo "a service process exited (status ${code}); stopping the container" >&2
  kill -TERM "${pids[@]}" 2>/dev/null
  wait
  exit "$code"
}

healthcheck() {
  local running
  running="$(cat "$ROLE_FILE" 2>/dev/null || echo all)"
  case "$running" in
    all)
      curl -fsS -o /dev/null http://127.0.0.1:8000/health/live
      curl -fsS -o /dev/null http://127.0.0.1:3000/healthz
      python -m app.cli healthcheck worker
      python -m app.cli healthcheck watcher
      ;;
    api) curl -fsS -o /dev/null http://127.0.0.1:8000/health/live ;;
    web) curl -fsS -o /dev/null http://127.0.0.1:3000/healthz ;;
    worker | watcher) python -m app.cli healthcheck "$running" ;;
    *) exit 0 ;;
  esac
}

case "$role" in
  healthcheck) healthcheck ;;
  all | api | web | watcher | worker | migrate) echo "$role" >"$ROLE_FILE" ;;
esac

case "$role" in
  healthcheck) ;;
  all) run_all ;;
  api) migrate && api ;;
  worker) worker "$@" ;;
  watcher) watcher ;;
  web) web ;;
  migrate) migrate ;;
  *) exec "$role" "$@" ;;
esac
