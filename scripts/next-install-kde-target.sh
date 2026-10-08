#!/bin/bash
set -euo pipefail
export SYSTEMD_OFFLINE=1
bash /mnt/host/scripts/next-mount-targets.sh
resize2fs /dev/vdc
target=/mnt/kde
for p in dev proc sys run; do mkdir -p "$target/$p"; mount --rbind "/$p" "$target/$p"; mount --make-rslave "$target/$p"; done
mkdir -p "$target/mnt/host"; mount --bind /mnt/host "$target/mnt/host"
cleanup() { umount "$target/mnt/host" || true; for p in run sys proc dev; do umount -R "$target/$p" || true; done; }
trap cleanup EXIT
chroot "$target" bash /mnt/host/scripts/guest-install-cached.sh kde
chroot "$target" pacman -Q > /mnt/host/vm/next/packages-kde-installed.txt
sync
