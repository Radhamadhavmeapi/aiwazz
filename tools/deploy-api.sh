#!/usr/bin/env bash
# Apply database migrations, restart voice-clone (if set up) and voice-api (PM2), then wait for /api/health.
set -euo pipefail
export PATH=/www/server/nodejs/v24.11.1/bin:$PATH
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/api"
.venv/bin/alembic upgrade head
if pm2 describe voice-clone >/dev/null 2>&1; then pm2 restart voice-clone >/dev/null; fi
pm2 restart voice-api >/dev/null
for i in $(seq 1 60); do
  [[ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8100/api/health)" == 200 ]] && { echo "voice-api healthy after ${i}s"; exit 0; }
  sleep 1
done
echo "voice-api did not become healthy; check: pm2 logs voice-api" >&2
exit 1
