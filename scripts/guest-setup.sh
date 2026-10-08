#!/bin/bash
set -eux
mountpoint -q /proc || mount -t proc proc /proc
mountpoint -q /sys || mount -t sysfs sysfs /sys
mountpoint -q /dev || mount -t devtmpfs devtmpfs /dev
mkdir -p /run /mnt/host
mountpoint -q /run || mount -t tmpfs tmpfs /run
modprobe 9pnet_virtio
mountpoint -q /mnt/host || mount -t 9p -o trans=virtio,version=9p2000.L hostshare /mnt/host
modprobe virtio_net
ip link set lo up
ip link set eth0 up
ip addr replace 10.0.2.15/24 dev eth0
ip route replace default via 10.0.2.2
rm -f /etc/resolv.conf
printf 'nameserver 10.0.2.3\n' >/etc/resolv.conf
set +x
source /mnt/host/vm/proxy.env
set -x
curl -I --max-time 20 http://os.archlinuxarm.org/aarch64/core/core.db
