#!/bin/bash
set -euo pipefail
grep -qw rock5t.builder=1 /proc/cmdline
mkdir -p /run /dev/pts /dev/shm /mnt/host
mountpoint -q /run || mount -t tmpfs tmpfs /run
mountpoint -q /dev/pts || mount -t devpts devpts /dev/pts
mountpoint -q /dev/shm || mount -t tmpfs tmpfs /dev/shm
mountpoint -q /mnt/host || mount -t 9p -o trans=virtio,version=9p2000.L hostshare /mnt/host
ln -sfn /proc/self/fd /dev/fd
ln -sfn /proc/self/fd/0 /dev/stdin
ln -sfn /proc/self/fd/1 /dev/stdout
ln -sfn /proc/self/fd/2 /dev/stderr
ip link set lo up
ip link set eth0 up
ip addr replace 10.0.2.15/24 dev eth0
ip route replace default via 10.0.2.2
rm -f /etc/resolv.conf; printf 'nameserver 10.0.2.3\n' > /etc/resolv.conf
[[ $(blkid -s UUID -o value /dev/vda) == $(cat /mnt/host/vm/next/builder-root.uuid) ]] || { echo "Not the selected build root" >&2; exit 1; }
source /mnt/host/vm/proxy.env
mkdir -p /sys/kernel/security
mountpoint -q /sys/kernel/security || mount -t securityfs securityfs /sys/kernel/security
uname -r; cat /sys/kernel/security/lsm
cp -a /mnt/host/kernel-next/payload/usr/lib/modules/6.18.44-current-rockchip64-landlock1 /usr/lib/modules/
pacman-key --init
pacman-key --populate archlinuxarm archlinux
mkdir -p /var/lib/pacman/sync
cp /mnt/host/vm/{core,extra,alarm,aur}.db /var/lib/pacman/sync/
pacman -Su --print --print-format '%l' > /mnt/host/vm/next-upgrade-urls.txt
source /mnt/host/scripts/profile-packages.sh
mapfile -t cli < <(grep -Ev '^[[:space:]]*(#|$)' /mnt/host/profiles/cli.packages)
pacman -Sp --print-format '%l' "${cli[@]}" > /mnt/host/vm/next-cli-urls.txt
