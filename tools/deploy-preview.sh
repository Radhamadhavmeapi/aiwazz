#!/usr/bin/env bash
# Build the dashboard design preview and deploy it to https://login.aiwazz.in/preview/
# Only ever writes inside $DEST (the preview/ folder), never the rest of the web root.
set -euo pipefail
export PATH=/www/server/nodejs/v24.11.1/bin:$PATH
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${DEST:-/www/wwwroot/login.aiwazz.in/preview}"
ROUTES=(tokens generate login signup history voices api-keys settings)

cd "$ROOT/dashboard"
npm ci --no-fund --no-audit --loglevel=error
npm run build:preview

OUT="$ROOT/dashboard/dist-preview"
mkdir -p "$OUT/samples"
cp "$ROOT"/landing/samples/*.mp3 "$ROOT"/landing/samples/samples.json "$OUT/samples/"
for r in "${ROUTES[@]}"; do mkdir -p "$OUT/$r" && cp "$OUT/index.html" "$OUT/$r/index.html"; done

[[ "${1:-}" == "--build-only" ]] && { echo "built: $OUT"; exit 0; }

case "$DEST" in /www/wwwroot/login.aiwazz.in/preview) ;; *) echo "refusing DEST=$DEST" >&2; exit 1;; esac
mkdir -p "$DEST"
rsync -a --delete "$OUT/" "$DEST/"
chown -R www:www "$DEST"
echo "deployed: $DEST ($(du -sh "$DEST" | cut -f1))"
