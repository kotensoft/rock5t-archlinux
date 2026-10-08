#!/bin/bash
set -euo pipefail
target=/mnt/kde
for p in dev proc sys run; do mount --rbind "/$p" "$target/$p"; mount --make-rslave "$target/$p"; done
mkdir -p "$target/mnt/host"
mount --bind /mnt/host "$target/mnt/host"
cleanup() { umount "$target/mnt/host" || true; for p in run sys proc dev; do umount -R "$target/$p" || true; done; }
trap cleanup EXIT
chroot "$target" bash /mnt/host/scripts/guest-install-cached.sh kde
sync
