#!/bin/bash
set -euo pipefail
bash /mnt/host/scripts/next-mount-targets.sh
python3 /mnt/host/scripts/qa-next-roots.py > /mnt/host/vm/next/root-policy-audit.json
for variant in cli kde; do
 fstrim -v "/mnt/$variant"
 umount "/mnt/$variant"
done
sync
: > /mnt/host/vm/next/shutdown.request
