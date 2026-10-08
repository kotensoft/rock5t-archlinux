#!/bin/bash
set -euo pipefail
variant=${1:?}; target=/mnt/$variant
chroot "$target" /usr/local/sbin/rock5t-kernel status --allow-unmounted-boot >"/mnt/host/vm/kernel-status-$variant.json"
[[ -s "$target/usr/lib/firmware/arm/mali/arch10.8/mali_csffw.bin" ]]
[[ -s "$target/usr/lib/firmware/rtl_nic/rtl8125b-2.fw" ]]
[[ ! -e "$target/etc/pacman.d/gnupg" ]]
[[ ! -s "$target/etc/machine-id" ]]
! grep -q '^alarm:' "$target/etc/passwd"
grep -q '^root:!:' "$target/etc/shadow"
! find "$target/etc/ssh" -name 'ssh_host_*' | grep -q .
mkdir -p "/mnt/host/boot-$variant"
cp -r --preserve=mode,timestamps "$target/boot/." "/mnt/host/boot-$variant/"
find "$target/boot" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
find "$target/var/cache/pacman/pkg" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
find "$target/var/log" -type f -delete
rm -f "$target/root/.bash_history"
rm -rf "$target/root/.gnupg" "$target/root/.ssh"
# No host shares, build scripts, credentials, or virtual-machine configuration ship.
find "$target/mnt" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
mkdir -p "$target/usr/share/rock5t-build"
cp /mnt/host/research/rock5t-armbian-sources.lock.json "$target/usr/share/rock5t-build/"
cp "/mnt/host/vm/packages-$variant-final.txt" "$target/usr/share/rock5t-build/packages.txt"
printf '%s\n' "$variant" >"$target/etc/rock5t/variant"
sync
