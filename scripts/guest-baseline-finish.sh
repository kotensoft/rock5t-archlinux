#!/bin/bash
set -euo pipefail
pacman-key --populate archlinuxarm archlinux
bash /mnt/host/scripts/guest-install-cached.sh cli
: "${ROCK5T_KERNEL_PACKAGE:?Pass the explicitly built next-version kernel package path}"
pacman -U --noconfirm "$ROCK5T_KERNEL_PACKAGE"
# Remove firmware for unrelated GPU/SoC vendors, retaining board Wi-Fi choices.
pacman -R --noconfirm linux-firmware linux-firmware-amd linux-firmware-amdgpu linux-firmware-nvidia linux-firmware-radeon linux-firmware-intel linux-firmware-cirrus linux-firmware-ti
sed -i 's/^#en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen
locale-gen
printf 'LANG=en_US.UTF-8\n' >/etc/locale.conf
ln -sfn /usr/share/zoneinfo/Etc/UTC /etc/localtime
mkdir -p /mnt/host/vm/baseline-boot
cp /boot/Image /mnt/host/vm/baseline-boot/Image
cp /boot/initramfs-linux.img /mnt/host/vm/baseline-boot/initramfs.img
cp /var/lib/pacman/sync/*.db /mnt/host/vm/
pacman -Q > /mnt/host/vm/packages-baseline.txt
# Preserve cached artifacts on host before removing build-only cache from images.
for f in /var/cache/pacman/pkg/*.pkg.tar.*; do
 [[ -f $f ]] || continue
 [[ -e /mnt/host/arch-packages/${f##*/} ]] || cp "$f" /mnt/host/arch-packages/
done
find /var/cache/pacman/pkg -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
sync
