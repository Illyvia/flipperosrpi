#!/usr/bin/env bash
set -euo pipefail
[[ -r /proc/device-tree/model ]] || { echo "No Raspberry Pi device-tree model found" >&2; exit 1; }
model=$(tr -d '\0' </proc/device-tree/model)
case "$model" in
 'Raspberry Pi 4 Model B '*|'Raspberry Pi 400 '*) ;;
 *) printf 'Unsupported model: %s\n' "$model" >&2; exit 1 ;;
esac
[[ $(uname -m) == aarch64 && $(getconf LONG_BIT) == 64 && $(dpkg --print-architecture) == arm64 ]] || {
 echo "A 64-bit ARM kernel and Debian arm64 userspace are required" >&2; exit 1;
}
printf 'Target: %s\nKernel: %s\n' "$model" "$(uname -r)"
getconf GNU_LIBC_VERSION
printf 'Target architecture check passed. This does not verify firmware or profile compatibility.\n'
