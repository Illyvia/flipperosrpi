#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
SRC=${UBOOT_SRC:-$ROOT/upstream/u-boot}
OUT=${UBOOT_OUT:-$ROOT/build/u-boot}
# Flipper's BLS implementation supplies profile ordering; the Pi board uses firmware DT.
[[ $(git -C "$SRC" rev-parse HEAD) == ec02432b1751e2749cc107477fbce20c0ed8c8b2 ]] || { echo 'Wrong U-Boot source revision' >&2; exit 1; }
PATCH="$ROOT/port/patches/flipper-uboot-pi.patch"
if git -C "$SRC" apply --check "$PATCH" 2>/dev/null; then git -C "$SRC" apply "$PATCH"
else git -C "$SRC" apply --reverse --check "$PATCH" >/dev/null || { echo 'U-Boot Pi patch does not match' >&2; exit 1; }; fi
make -C "$SRC" O="$OUT" CROSS_COMPILE=aarch64-linux-gnu- rpi_arm64_defconfig
# A FAT rescue script is independent of the Btrfs root filesystem.
grep -q '^recovery=' "$SRC/board/raspberrypi/rpi/rpi.env" || printf '\nrecovery=load mmc 0:1 ${scriptaddr} recovery/boot.scr; source ${scriptaddr}\n' >> "$SRC/board/raspberrypi/rpi/rpi.env"
grep -q '^fdtoverlay_addr_r=' "$SRC/board/raspberrypi/rpi/rpi.env" || printf '\nfdtoverlay_addr_r=0x0a000000\n' >> "$SRC/board/raspberrypi/rpi/rpi.env"
"$SRC/scripts/config" --file "$OUT/.config" --enable FS_BTRFS --enable CMD_BTRFS --enable BOOTMETH_BLS --enable BOOTSTD_FULL --enable CMD_BOOTFLOW_FULL \
 --set-val SYS_BOOTCOUNT_ADDR 0x05400000 --enable FAT_WRITE --enable BOOTCOUNT_LIMIT --enable BOOTCOUNT_FS --set-val BOOTCOUNT_BOOTLIMIT 3 \
 --set-str SYS_BOOTCOUNT_FS_INTERFACE mmc --set-str SYS_BOOTCOUNT_FS_DEVPART 0:1 \
 --set-str SYS_BOOTCOUNT_FS_NAME flipper-bootcount.bin --set-str BOOTCOUNT_ALTBOOTCMD 'run recovery' \
 --set-val BOOTDELAY 3 --set-str BOOTCOMMAND 'setenv bootmeths bls; if test -e mmc 0:1 /force-recovery; then run recovery; fi; bootflow scan -lb; run recovery'
make -C "$SRC" O="$OUT" CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
python3 "$ROOT/port/validate-uboot.py" "$OUT/.config"
make -C "$SRC" -j4 O="$OUT" CROSS_COMPILE=aarch64-linux-gnu-
python3 "$ROOT/port/validate-uboot.py" "$OUT/.config" "$OUT/u-boot.bin"
mkdir -p "$ROOT/build/full-os"
install -m644 "$OUT/u-boot.bin" "$ROOT/build/full-os/u-boot.bin"
cp "$OUT/.config" "$ROOT/build/full-os/u-boot.config"
