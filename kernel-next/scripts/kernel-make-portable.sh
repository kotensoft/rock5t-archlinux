#!/usr/bin/env bash
# Use an installed cross-toolchain. Original extracted-toolchain wrapper is retained separately.
set -euo pipefail
N=$(cd "$(dirname "$0")/.." && pwd)
export KBUILD_BUILD_USER=build KBUILD_BUILD_HOST=rock5t-source-build
export KBUILD_BUILD_TIMESTAMP='2026-08-18 04:32:26 +0000'
export SOURCE_DATE_EPOCH=1787027546
exec make -C "$N/linux-6.18.44" O="$N/build/board" \
  ARCH=arm64 CROSS_COMPILE="${CROSS_COMPILE:-aarch64-linux-gnu-}" \
  HOSTCC="${HOSTCC:-gcc}" LOCALVERSION=-current-rockchip64-landlock1 \
  KCFLAGS=-Wno-error=misleading-indentation "$@"
