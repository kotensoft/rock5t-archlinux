#!/bin/bash
set -euo pipefail
grep -qw rock5t.builder=1 /proc/cmdline
mkdir -p /run /dev/pts /dev/shm /mnt/cli /mnt/kde
mountpoint -q /run || mount -t tmpfs tmpfs /run
mountpoint -q /dev/pts || mount -t devpts devpts /dev/pts
mountpoint -q /dev/shm || mount -t tmpfs tmpfs /dev/shm
ln -sfn /proc/self/fd /dev/fd
ln -sfn /proc/self/fd/0 /dev/stdin
ln -sfn /proc/self/fd/1 /dev/stdout
ln -sfn /proc/self/fd/2 /dev/stderr
mountpoint -q /mnt/cli || mount /dev/vdb /mnt/cli
mountpoint -q /mnt/kde || mount /dev/vdc /mnt/kde
