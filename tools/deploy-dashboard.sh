#!/usr/bin/env bash
# Build the dashboard (production) and deploy it to https://login.aiwazz.in (/www/wwwroot/login.aiwazz.in).
# Keeps: preview/ (design preview), aaPanel files (.user.ini, .htaccess, .well-known/, 404.html, 502.html).
# nginx: deploy/nginx/login.aiwazz.in.conf (proxy /api/, SPA fallback) must be installed.
set -euo pipefail
export PATH=/www/server/nodejs/v24.11.1/bin:$PATH
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST=/www/wwwroot/login.aiwazz.in

cd "$ROOT/dashboard"
npm ci --no-fund --no-audit --loglevel=error
npm run build >/dev/null
mkdir -p dist/samples && cp "$ROOT"/landing/samples/*.mp3 dist/samples/
[[ "${1:-}" == "--build-only" ]] && { echo "built: $ROOT/dashboard/dist"; exit 0; }

rsync -a --delete \
  --exclude='/preview/' --exclude='/.user.ini' --exclude='/.htaccess' --exclude='/.well-known/' \
  --exclude='/404.html' --exclude='/502.html' \
  "$ROOT/dashboard/dist/" "$DEST/"
find "$DEST" -mindepth 1 -maxdepth 1 ! -name '.user.ini' ! -name '.well-known' -exec chown -R www:www {} +
echo "deployed: $DEST"
