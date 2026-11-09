#!/usr/bin/env bash
# Run directly on the physical Pi; no emulator or installation required.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
bash "$ROOT/scripts/check-target.sh"
command -v curl >/dev/null || { echo "curl is required" >&2; exit 1; }
BIN="$ROOT/build/stage/usr/local/bin/flipctl"
ASSETS="$ROOT/build/stage/usr/local/share/flipctl/assets/remote"
[[ -x "$BIN" ]] || { echo "Build/staged binary is missing" >&2; exit 1; }
TMP=$(mktemp -d)
pid=
cleanup() {
 if [[ -n "$pid" ]]; then kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; fi
 rm -f -- "$TMP/frame.png" "$TMP/ui.log" "$TMP/page.html"
 rmdir -- "$TMP" 2>/dev/null || true
}
trap cleanup EXIT
"$BIN" --png "$TMP/frame.png"
[[ -s "$TMP/frame.png" ]] || { echo "PNG render failed" >&2; exit 1; }
# Port 18899 keeps this check separate from an installed service on 8899.
if curl --silent --max-time 1 http://127.0.0.1:18899/ >/dev/null; then
 echo "Port 18899 is occupied; stop its owner before testing" >&2; exit 1
fi
"$BIN" --headless --remote 127.0.0.1:18899 --assets "$ASSETS" >"$TMP/ui.log" 2>&1 &
pid=$!
ready=0
for attempt in {1..30}; do
 kill -0 "$pid" 2>/dev/null || { cat "$TMP/ui.log" >&2; exit 1; }
 if curl --fail --silent --max-time 1 http://127.0.0.1:18899/ >"$TMP/page.html"; then ready=1; break; fi
 sleep 1
done
[[ "$ready" == 1 && -s "$TMP/page.html" ]] || { cat "$TMP/ui.log" >&2; exit 1; }
printf 'PASS: ARM64 program rendered a PNG and served its browser UI on the physical Pi.\n'
