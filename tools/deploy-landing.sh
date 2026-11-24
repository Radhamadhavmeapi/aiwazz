#!/usr/bin/env bash
# Build the Astro landing page and deploy it to https://aiwazz.in (/www/wwwroot/aiwazz.in).
# Keeps aaPanel/SSL files in place: .user.ini, .htaccess, .well-known/ (ACME), 502.html.
set -euo pipefail
export PATH=/www/server/nodejs/v24.11.1/bin:$PATH
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST=/www/wwwroot/aiwazz.in

# Changelog entries published in the admin panel → src/data/changelog.generated.json (gitignored), read by /changelog/.
OUT="$ROOT/landing/src/data/changelog.generated.json"
if ! (cd "$ROOT/api" && .venv/bin/python -m admin.announcements > "$OUT.tmp" 2>/dev/null); then echo "[]" > "$OUT.tmp"; fi
mv "$OUT.tmp" "$OUT"

cd "$ROOT/landing"
npm ci --no-fund --no-audit --loglevel=error
npm run build >/dev/null
[[ "${1:-}" == "--build-only" ]] && { echo "built: $ROOT/landing/dist"; exit 0; }

rsync -a --delete \
  --exclude='.user.ini' --exclude='.htaccess' --exclude='.well-known/' --exclude='502.html' \
  "$ROOT/landing/dist/" "$DEST/"
# Ownership for deployed files only (not .user.ini, which aaPanel keeps immutable, or .well-known/)
find "$DEST" -mindepth 1 -maxdepth 1 ! -name '.user.ini' ! -name '.well-known' -exec chown -R www:www {} +
echo "deployed: $DEST ($(du -sh "$DEST" | cut -f1))"
