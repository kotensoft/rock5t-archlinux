#!/bin/bash
set -euo pipefail
mount -t proc proc /proc || true
mount -t sysfs sysfs /sys || true
mount -t devtmpfs devtmpfs /dev || true
mkdir -p /run /dev/pts /dev/shm /mnt/host /mnt/cli /mnt/kde
mount -t tmpfs tmpfs /run || true
mount -t devpts devpts /dev/pts || true
mount -t tmpfs tmpfs /dev/shm || true
ln -sfn /proc/self/fd /dev/fd
ln -sfn /proc/self/fd/0 /dev/stdin
ln -sfn /proc/self/fd/1 /dev/stdout
ln -sfn /proc/self/fd/2 /dev/stderr
modprobe 9pnet_virtio
mountpoint -q /mnt/host || mount -t 9p -o trans=virtio,version=9p2000.L hostshare /mnt/host
mount /dev/vdb /mnt/cli
mount /dev/vdc /mnt/kde
fstrim -v /
fstrim -v /mnt/cli
fstrim -v /mnt/kde
