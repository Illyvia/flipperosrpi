#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
STAGE="$ROOT/build/stage"
BIN="$STAGE/usr/local/bin/flipctl"
[[ -f "$BIN" ]] || { echo "Run build-ui.sh first" >&2; exit 1; }
command -v readelf >/dev/null
readelf -h "$BIN" | grep -q 'Machine:.*AArch64' || { echo "Not an ARM64 executable" >&2; exit 1; }
WORK=$(mktemp -d "$ROOT/build/package.XXXXXX")
OUT="$WORK/flipper-ui-rpi4-arm64"
mkdir -p "$OUT"
cp -a "$STAGE" "$OUT/"
mkdir -p "$OUT/scripts"
cp "$ROOT/scripts/check-target.sh" "$ROOT/scripts/smoke-native.sh" "$OUT/scripts/"
# smoke-native expects build/stage relative to the project root.
mkdir -p "$OUT/build"
mv "$OUT/stage" "$OUT/build/stage"
cp "$ROOT/README.md" "$ROOT/sources.lock.json" "$OUT/"
mkdir -p "$OUT/licenses"
cp "$ROOT/upstream/flipctl/LICENSE" "$OUT/licenses/flipctl-LICENSE"
cp "$ROOT/upstream/flipctl/THIRD-PARTY-LICENSES.md" "$OUT/licenses/"
for font in "$ROOT"/upstream/flipctl/third_party/flipctl-fonts/*; do
 [[ -f "$font/LICENSE" ]] || continue
 cp "$font/LICENSE" "$OUT/licenses/font-$(basename "$font")-LICENSE"
done
readelf --version-info "$BIN" > "$OUT/elf-versions.txt"
(cd "$OUT" && sha256sum build/stage/usr/local/bin/flipctl > SHA256SUMS)
tar --mode="u=rwX,go=rX" -C "$WORK" -czf "$ROOT/build/flipper-ui-rpi4-arm64.tar.gz" flipper-ui-rpi4-arm64
sha256sum "$ROOT/build/flipper-ui-rpi4-arm64.tar.gz"
