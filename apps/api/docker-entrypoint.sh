#!/bin/sh
set -e
# API runs migrations by default. Set RUN_DB_MIGRATIONS=0 on Celery workers to avoid concurrent migration races.
if [ "${RUN_DB_MIGRATIONS:-1}" = "1" ]; then
  echo "[api] Running Alembic migrations..."
  alembic upgrade head
fi
exec "$@"
