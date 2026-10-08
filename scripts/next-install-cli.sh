#!/bin/bash
set -euo pipefail
grep -qw rock5t.builder=1 /proc/cmdline
source /mnt/host/vm/proxy.env
for phase in upgrade cli; do
 while IFS= read -r url; do
  case "$url" in http*) f=${url##*/}; cp -u "/mnt/host/arch-packages/$f" /var/cache/pacman/pkg/; cp "/mnt/host/arch-packages/$f.sig" /var/cache/pacman/pkg/;; esac
 done < "/mnt/host/vm/next-$phase-urls.txt"
done
pacman -Su --noconfirm
source /mnt/host/scripts/profile-packages.sh
install_profile cli
pacman -U --noconfirm /mnt/host/packages/linux-rock5t-6.18.44-2-aarch64.pkg.tar.zst
pacman -R --noconfirm linux-firmware linux-firmware-amd linux-firmware-amdgpu linux-firmware-nvidia linux-firmware-radeon linux-firmware-intel linux-firmware-cirrus linux-firmware-ti
sed -i 's/^#en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen
locale-gen
printf 'LANG=en_US.UTF-8\n' >/etc/locale.conf
ln -sfn /usr/share/zoneinfo/Etc/UTC /etc/localtime
python3 /mnt/host/overlay-work/tests/test_ssh_parser.py > /mnt/host/vm/next/target-openssh-parser.log 2>&1
pacman -Q > /mnt/host/vm/next/packages-cli-baseline.txt
mapfile -t kde < <(grep -Ev '^[[:space:]]*(#|$)' /mnt/host/profiles/kde.packages)
pacman -Sp --print-format '%l' "${kde[@]}" > /mnt/host/vm/next-kde-urls.txt
# The active build kernel's drivers are already loaded; this manual test copy
# must not masquerade as a managed target generation in image clones.
rm -rf /usr/lib/modules/6.18.44-current-rockchip64-landlock1
find /var/cache/pacman/pkg -mindepth 1 -maxdepth 1 -type f -delete
sync
