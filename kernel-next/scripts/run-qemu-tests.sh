#!/usr/bin/env bash
set -euo pipefail
N=$(cd "$(dirname "$0")/.." && pwd)
T=$(cd "$N/../host-tools/root" && pwd)
export LD_LIBRARY_PATH="$T/usr/lib/x86_64-linux-gnu"
exec "$T/usr/bin/qemu-system-aarch64" \
  -M virt -cpu cortex-a72 -accel tcg -m 1536 -smp 2 \
  -nographic -no-reboot -nic none \
  -kernel "$N/build/board/arch/arm64/boot/Image" \
  -initrd "$N/build/landlock-tests.cpio.gz" \
  -append 'console=ttyAMA0 rdinit=/init loglevel=5 rt_group_sched=0'
