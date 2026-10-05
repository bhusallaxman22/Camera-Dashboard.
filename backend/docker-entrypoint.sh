#!/bin/sh
set -e

role="${1:-api}"
shift || true

case "$role" in
  api)
    python -m app.cli init-dirs
    echo "Running database migrations..."
    alembic upgrade head
    # Open SSE streams never finish on their own; cap graceful shutdown so
    # `docker stop` doesn't hang until SIGKILL.
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
      --proxy-headers --forwarded-allow-ips='*' --no-access-log \
      --timeout-graceful-shutdown 5
    ;;
  worker)
    exec python -m app.workers.run "$@"
    ;;
  watcher)
    exec python -m app.watchers.run
    ;;
  *)
    exec "$role" "$@"
    ;;
esac
