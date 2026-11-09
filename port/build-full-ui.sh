#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
SRC="$ROOT/upstream/flipctl"
PATCH="$ROOT/port/patches/flipctl-raspberry-pi.patch"
if git -C "$SRC" apply --check "$PATCH" 2>/dev/null; then git -C "$SRC" apply "$PATCH"
else git -C "$SRC" apply --reverse --check "$PATCH" >/dev/null || { echo 'Pi patch does not match this checkout' >&2; exit 1; }; fi
export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER=aarch64-linux-gnu-gcc
export CC_aarch64_unknown_linux_gnu=aarch64-linux-gnu-gcc
cargo build --manifest-path "$SRC/Cargo.toml" --locked --release --target aarch64-unknown-linux-gnu \
 -p flipctl --features device,slint,remote,wayland,gpu,raspberry-pi
OUT_DIR=${FLIPPER_BUILD_OUT:-"$ROOT/build/full-os"}
mkdir -p "$OUT_DIR"
install -m755 "$SRC/target/aarch64-unknown-linux-gnu/release/flipctl" "$OUT_DIR/flipctl"
