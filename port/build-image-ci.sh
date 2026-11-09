#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
[[ $(uname -m) == aarch64 && $EUID == 0 ]] || { echo 'Native ARM64 root required'; exit 1; }
preset=${1:-hdmi}
tint=${2:-orange}
[[ $preset == hdmi || $preset == waveshare-7-e ]]
[[ $tint == orange || $tint == grayscale ]]
export FLIPPER_BUILD_ROOT=${FLIPPER_BUILD_ROOT:-$ROOT/build/image}
export FLIPPER_BOARD_INPUT="$ROOT/build/board-inputs"
export FLIPPER_BOARD_CMDLINE='console=ttyS0,115200 cfg80211.ieee80211_regdom=00'
export FLIPPER_FDTOVERLAY="$ROOT/build/dsi-tools/fdtoverlay-host"
unset FLIPPER_PRIVATE_WIFI_FILE
mkdir -p "$FLIPPER_BUILD_ROOT/artifacts"
cp -a "$ROOT/port" "$FLIPPER_BUILD_ROOT/port"
cp "$ROOT/build/full-os/flipctl" "$ROOT/build/full-os/u-boot.bin" "$FLIPPER_BUILD_ROOT/artifacts/"
python3 "$ROOT/port/prepare-board-inputs.py" "$FLIPPER_BOARD_INPUT"
python3 "$ROOT/port/import-upstream.py" "$FLIPPER_BUILD_ROOT"
python3 "$ROOT/port/configure-image.py"
python3 "$ROOT/port/configure-mesa.py"
python3 "$ROOT/port/finalize-image.py"
python3 "$ROOT/port/configure-display.py" --image "$FLIPPER_BUILD_ROOT/flipperos-rpi4.img" \
 --project "$ROOT" --metadata "$FLIPPER_BUILD_ROOT/image-board.json" \
 --dtmerge "$ROOT/build/dsi-tools/dtmerge-host" --preset "$preset" --tint "$tint" \
 --report "$FLIPPER_BUILD_ROOT/display-validation.json"
python3 "$ROOT/port/check-public-image.py" "$FLIPPER_BUILD_ROOT/flipperos-rpi4.img" "$FLIPPER_BUILD_ROOT/image-board.json"
mkdir -p "$ROOT/build/download"
name="flipperos-rpi4-1328001-$preset-$tint"
zstd -T2 -3 --check -c "$FLIPPER_BUILD_ROOT/flipperos-rpi4.img" > "$ROOT/build/download/$name.img.zst"
(cd "$ROOT/build/download" && sha256sum "$name.img.zst" > "$name.img.zst.sha256")
cp "$FLIPPER_BUILD_ROOT/validation.json" "$FLIPPER_BUILD_ROOT/display-validation.json" "$FLIPPER_BUILD_ROOT/public-image-check.json" "$ROOT/build/download/"
cp "$ROOT/sources.lock.json" "$FLIPPER_BOARD_INPUT/board-packages.json" "$ROOT/build/download/"
