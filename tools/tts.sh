#!/usr/bin/env bash
# AiWazz text-to-speech from the command line (for the Remotion / video pipeline).
#
#   export AIWAZZ_API_KEY=aiw_live_...          # create one at https://login.aiwazz.in/api-keys
#   tools/tts.sh -v hf_alpha -o hook.mp3 "Raat 11 baje customer ne call kiya" --hinglish
#   tools/tts.sh -v am_michael -f wav -s 1.1 -o intro.wav < script.txt
#
# Options
#   -o FILE        output file (required); format from -f or the extension (.mp3/.wav)
#   -v VOICE       voice id (default hf_alpha), see: tools/tts.sh --voices
#   -f FORMAT      mp3 | wav
#   -s SPEED       0.7 – 1.3 (default 1.0)
#   -l LUFS        loudness target -30 … -8 (default -14); --no-normalize to skip
#   --hinglish     Roman Hindi → Devanagari before synthesis (Hindi voices)
#   --voices       list voices and exit
#   TEXT           the script; if omitted, read from stdin
# Env: AIWAZZ_API_KEY (required), AIWAZZ_API_URL (default https://login.aiwazz.in)
# Prints the duration in seconds on success. Exit codes: 0 ok, 1 usage, 2 API/network error.
set -euo pipefail

API="${AIWAZZ_API_URL:-https://login.aiwazz.in}"
VOICE="hf_alpha"; FORMAT=""; SPEED="1.0"; LUFS="-14"; NORMALIZE=true; HINGLISH=false; OUT=""; TEXT=""

die() { echo "tts.sh: $1" >&2; exit "${2:-1}"; }
command -v curl >/dev/null || die "curl is required"
command -v python3 >/dev/null || die "python3 is required"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -o) OUT="${2:?}"; shift 2 ;;
    -v) VOICE="${2:?}"; shift 2 ;;
    -f) FORMAT="${2:?}"; shift 2 ;;
    -s) SPEED="${2:?}"; shift 2 ;;
    -l) LUFS="${2:?}"; shift 2 ;;
    --no-normalize) NORMALIZE=false; shift ;;
    --hinglish) HINGLISH=true; shift ;;
    --voices)
      curl -fsS "$API/api/voices" | python3 -c '
import json, sys
for v in json.load(sys.stdin)["voices"]:
    print("%-12s %-13s %-6s %s" % (v["id"], v["lang_name"], v["gender"], v["name"]))'
      exit 0 ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) die "unknown option $1" ;;
    *) TEXT="$1"; shift ;;
  esac
done

[[ -n "${AIWAZZ_API_KEY:-}" ]] || die "set AIWAZZ_API_KEY (create a key at $API/api-keys)"
[[ -n "$OUT" ]] || die "-o FILE is required"
if [[ -z "$FORMAT" ]]; then case "$OUT" in *.wav) FORMAT=wav ;; *) FORMAT=mp3 ;; esac; fi
[[ "$FORMAT" == mp3 || "$FORMAT" == wav ]] || die "format must be mp3 or wav"
[[ -n "$TEXT" ]] || TEXT="$(cat)"
[[ -n "${TEXT//[[:space:]]/}" ]] || die "no text given"

BODY="$(TEXT="$TEXT" VOICE="$VOICE" FORMAT="$FORMAT" SPEED="$SPEED" LUFS="$LUFS" NORMALIZE="$NORMALIZE" HINGLISH="$HINGLISH" python3 -c '
import json, os
e = os.environ
print(json.dumps({"text": e["TEXT"], "voice": e["VOICE"], "format": e["FORMAT"], "speed": float(e["SPEED"]),
                  "loudness_lufs": float(e["LUFS"]), "normalize": e["NORMALIZE"] == "true",
                  "transliterate": e["HINGLISH"] == "true"}))')"

TMP="$(mktemp)"; trap 'rm -f "$TMP"' EXIT
CODE="$(curl -sS -o "$TMP" -w '%{http_code}' -X POST "$API/api/tts?wait=true" \
  -H "X-API-Key: $AIWAZZ_API_KEY" -H 'Content-Type: application/json' --data-binary "$BODY" --max-time 320)" \
  || die "network error talking to $API" 2

read -r STATUS URL DUR <<<"$(python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
print(d.get("status", "error"), (d.get("urls") or {}).get(sys.argv[2], "-"), d.get("duration_sec", "-"))' "$TMP" "$FORMAT" 2>/dev/null || echo "error - -")"

if [[ "$CODE" != 200 || "$STATUS" != done ]]; then
  MSG="$(python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
m = d.get("detail") or d.get("error") or d.get("status")
if isinstance(m, list):
    m = "; ".join(str(x.get("msg", x)).replace("Value error, ", "") for x in m)
print(m)' "$TMP" 2>/dev/null || cat "$TMP")"
  [[ "$CODE" == 202 ]] && MSG="still running after 290 s (queue busy); check History"
  die "HTTP $CODE: $MSG" 2
fi

curl -fsS -H "X-API-Key: $AIWAZZ_API_KEY" -o "$OUT" "$API$URL" || die "download failed" 2
echo "$DUR"
