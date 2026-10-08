#!/usr/bin/env bash
set -euo pipefail
N=$(cd "$(dirname "$0")/.." && pwd)
T=$(cd "$N/../host-tools/root" && pwd)
export PATH="$T/usr/bin:$PATH"
export LD_LIBRARY_PATH="$T/usr/lib/x86_64-linux-gnu"
mkdir -p "$N/build/selftests"
make -C "$N/linux-6.18.44" O="$N/build/headers" ARCH=arm64 HOSTCC=/usr/bin/gcc headers
make -C "$N/linux-6.18.44/tools/testing/selftests/landlock" \
  OUTPUT="$N/build/selftests" CC="$T/usr/bin/aarch64-linux-gnu-gcc" \
  KHDR_INCLUDES="-I$N/build/headers/usr/include -I$N/arm-extra/usr/include" \
  LDFLAGS="-static -L$N/arm-extra/usr/lib/aarch64-linux-gnu" -j4
