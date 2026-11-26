#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

echo "Starting Postgres (pgvector) on :5434 ..."
docker compose up -d db

echo "Waiting for DB healthy..."
for i in {1..30}; do
  if docker compose exec -T db pg_isready -U trainer -d trainer >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# If volume already existed before init script mounted, apply migration idempotently
docker compose exec -T db psql -U trainer -d trainer -f /docker-entrypoint-initdb.d/001_init.sql >/dev/null 2>&1 || true

cd "$ROOT/backend"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt
cp -n "$ROOT/.env" .env 2>/dev/null || true

echo "API on http://127.0.0.1:8000  (docs at /docs)"
exec uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
