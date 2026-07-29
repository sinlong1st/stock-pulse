#!/bin/sh
# Container entrypoint: apply DB migrations, then run the app.
set -e

mkdir -p /app/data

echo "[stockpulse] Applying database migrations (alembic upgrade head)..."
alembic upgrade head

echo "[stockpulse] Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
