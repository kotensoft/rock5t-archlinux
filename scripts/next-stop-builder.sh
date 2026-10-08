#!/bin/bash
set -euo pipefail
grep -qw rock5t.builder=1 /proc/cmdline
sync
fstrim -v / || true
: > /mnt/host/vm/next/shutdown.request
