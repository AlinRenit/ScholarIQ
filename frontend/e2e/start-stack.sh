#!/usr/bin/env bash
# Start a throwaway ScholarIQ stack for the end-to-end tests, with outbound
# network access blocked. Used by playwright.config.ts; it can also be run by
# hand. Expects `npm run build` to have been run and the backend installed.
#
#   E2E_DIR        working directory for the database, uploads and logs
#   E2E_API_PORT   backend port (default 8100)
#   E2E_WEB_PORT   web port (default 3100)
#   SCHOLARIQ_PY   Python interpreter with the backend installed
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
E2E_DIR="${E2E_DIR:-${TMPDIR:-/tmp}/scholariq-e2e}"
API_PORT="${E2E_API_PORT:-8100}"
WEB_PORT="${E2E_WEB_PORT:-3100}"
if [[ -z "${SCHOLARIQ_PY:-}" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then SCHOLARIQ_PY="$ROOT/.venv/bin/python"; else SCHOLARIQ_PY=python3; fi
fi

rm -rf "$E2E_DIR"
mkdir -p "$E2E_DIR/uploads"

# Offline: no proxy, and every non-loopback connection is refused and logged.
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy NO_PROXY no_proxy
export SCHOLARIQ_NET_GUARD_LOG="$E2E_DIR/outbound.log"
: > "$SCHOLARIQ_NET_GUARD_LOG"

export SCHOLARIQ_ENVIRONMENT=test
export SCHOLARIQ_DATABASE_URL="sqlite:///$E2E_DIR/scholariq.db"
export SCHOLARIQ_UPLOAD_DIR="$E2E_DIR/uploads"
export SCHOLARIQ_CONTENT_DIR="$ROOT/content"
export SCHOLARIQ_SECRET_KEY="e2e-only-secret-key-not-for-real-use"
export SCHOLARIQ_CORS_ORIGINS="[\"http://127.0.0.1:$WEB_PORT\"]"

api_pid=""
cleanup() { [[ -n "$api_pid" ]] && kill "$api_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

cd "$ROOT/backend"
PYTHONPATH="$HERE/offline" "$SCHOLARIQ_PY" -m alembic upgrade head > "$E2E_DIR/migrate.log" 2>&1
PYTHONPATH="$HERE/offline" "$SCHOLARIQ_PY" -m scholariq.curriculum.sync >> "$E2E_DIR/migrate.log" 2>&1
PYTHONPATH="$HERE/offline" "$SCHOLARIQ_PY" -m uvicorn scholariq.main:create_app --factory \
  --host 127.0.0.1 --port "$API_PORT" > "$E2E_DIR/api.log" 2>&1 &
api_pid=$!

cd "$ROOT/frontend"
export NEXT_TELEMETRY_DISABLED=1
export SCHOLARIQ_API_URL="http://127.0.0.1:$API_PORT"
export NODE_OPTIONS="--require $HERE/offline/net-guard.cjs"
# The production build is standalone (as in the Docker image): copy the static
# assets next to its server, as the Dockerfile does, and run it directly.
if [[ ! -f .next/standalone/server.js ]]; then
  echo "No production build found. Run 'npm run build' first." >&2
  exit 1
fi
rm -rf .next/standalone/.next/static
cp -r .next/static .next/standalone/.next/static
[[ -d public ]] && cp -r public .next/standalone/
status=0
HOSTNAME=127.0.0.1 PORT="$WEB_PORT" node .next/standalone/server.js || status=$?
exit "$status"
