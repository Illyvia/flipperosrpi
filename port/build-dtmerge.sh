#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
SRC=${RPI_UTILS_SRC:-$ROOT/upstream/raspberrypi-utils}
UBOOT=${UBOOT_SRC:-$ROOT/upstream/u-boot}
[[ $(git -C "$SRC" rev-parse HEAD) == 8c49aa29fa476271da4aa47c7e5c07c0ada6767f ]]
[[ $(git -C "$UBOOT" rev-parse HEAD) == ec02432b1751e2749cc107477fbce20c0ed8c8b2 ]]
mkdir -p "$ROOT/build/full-os" "$ROOT/build/dsi-tools"
fdt="$UBOOT/scripts/dtc/libfdt"
for target in host arm64; do
 if [[ $target == host ]]; then cc=gcc; out="$ROOT/build/dsi-tools/dtmerge-host"
 else cc=aarch64-linux-gnu-gcc; out="$ROOT/build/full-os/dtmerge"; fi
 "$cc" -O2 -I"$fdt" -I"$SRC/dtmerge" "$SRC/dtmerge/dtmerge.c" \
  "$SRC/dtmerge/dtoverlay.c" "$fdt"/*.c -o "$out"
done
# Validate with the same libfdt implementation as the bootloader. Ubuntu's older
# fdtoverlay rejects these modern Pi overlays even against an unmodified DTB.
dtc_src="$UBOOT/scripts/dtc"
gcc -O2 -I"$dtc_src" -I"$fdt" "$dtc_src/fdtoverlay.c" "$dtc_src/util.c" \
 "$fdt"/*.c -o "$ROOT/build/dsi-tools/fdtoverlay-host"
