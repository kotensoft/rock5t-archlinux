#!/bin/bash
set -euo pipefail
export SYSTEMD_OFFLINE=1
bash /mnt/host/scripts/next-mount-targets.sh
for variant in cli kde; do
 echo "FINALIZE_BEGIN=$variant"
 bash /mnt/host/scripts/finalize-target.sh "$variant" > "/mnt/host/vm/next/finalize-$variant.log" 2>&1
 echo "FINALIZE_PASS=$variant"
done
sync
