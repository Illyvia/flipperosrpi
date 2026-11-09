#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
SRC="$ROOT/upstream/flipctl"
TARGET_DIR=${CARGO_TARGET_DIR:-$SRC/target}
export CARGO_TARGET_DIR="$TARGET_DIR"
command -v cargo >/dev/null || { echo "Install Rust 1.92 or newer first." >&2; exit 1; }
[[ -f "$SRC/Cargo.lock" ]] || { echo "Missing upstream/flipctl checkout" >&2; exit 1; }
case "$(uname -m)" in
 aarch64) target=(); binary="$TARGET_DIR/release/flipctl" ;;
 x86_64) command -v aarch64-linux-gnu-gcc >/dev/null || { echo "Install gcc-aarch64-linux-gnu and rustup target add aarch64-unknown-linux-gnu" >&2; exit 1; }
 export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER=aarch64-linux-gnu-gcc
 target=(--target aarch64-unknown-linux-gnu)
 binary="$TARGET_DIR/aarch64-unknown-linux-gnu/release/flipctl" ;;
 *) echo "Unsupported build host architecture" >&2; exit 1 ;;
esac
# device is required by upstream's event loop even in --headless mode.
cargo build --manifest-path "$SRC/Cargo.toml" --locked --release -p flipctl --features device,slint,remote "${target[@]}"
STAGE="$ROOT/build/stage"
install -D -m755 "$binary" "$STAGE/usr/local/bin/flipctl"
mkdir -p "$STAGE/usr/local/share/flipctl/assets"
cp -a "$SRC/crates/flipper-ui/assets/remote" "$STAGE/usr/local/share/flipctl/assets/"
install -D -m644 "$ROOT/systemd/flipctl-rpi.service" "$STAGE/etc/systemd/system/flipctl-rpi.service"
printf 'Staged Raspberry Pi ARM64 UI in %s\n' "$STAGE"
