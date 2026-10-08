#!/usr/bin/env bash
set -euo pipefail
N=$(cd "$(dirname "$0")/.." && pwd)
T=$(cd "$N/../host-tools/root" && pwd)
X="$N/host-extra"
export PATH="$X/usr/bin:$T/usr/bin:$PATH"
export LD_LIBRARY_PATH="$X/usr/lib/x86_64-linux-gnu:$T/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export BISON_PKGDATADIR="$T/usr/share/bison"
export M4="$X/usr/bin/m4"
export KBUILD_BUILD_USER=build KBUILD_BUILD_HOST=rock5t-cloud-test
export KBUILD_BUILD_TIMESTAMP='2026-08-18 04:32:26 +0000'
export SOURCE_DATE_EPOCH=1787027546
exec make -C "$N/linux-6.18.44" O="$N/build/board" \
  ARCH=arm64 CROSS_COMPILE="$T/usr/bin/aarch64-linux-gnu-" \
  HOSTCC=/usr/bin/gcc \
  HOSTCFLAGS="-O2 --sysroot=$T" \
  HOSTLDFLAGS="--sysroot=$T -L$T/usr/lib/x86_64-linux-gnu" \
  USERCFLAGS="--sysroot=$T" USERLDFLAGS="--sysroot=$T" \
  LOCALVERSION=-current-rockchip64-landlock1 \
  KCFLAGS=-Wno-error=misleading-indentation "$@"
