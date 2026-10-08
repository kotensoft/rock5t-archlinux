#!/bin/bash
set -euo pipefail
export SYSTEMD_OFFLINE=1
bash /mnt/host/scripts/next-mount-targets.sh
variant=kde; target=/mnt/kde
for p in dev proc sys run; do mkdir -p "$target/$p"; mount --rbind "/$p" "$target/$p"; mount --make-rslave "$target/$p"; done
cleanup() { for p in run sys proc dev; do umount -R "$target/$p" || true; done; }
trap cleanup EXIT
systemd-analyze --root="$target" --man=no verify rock5t-firstboot@tty1.service rock5t-firstboot@ttyS2.service rock5t-provisioned.target plasmalogin.service > /mnt/host/vm/next/systemd-kde-verify-runtime.log 2>&1
chroot "$target" pacman -Q >"/mnt/host/vm/next/packages-$variant-final.txt"
chroot "$target" pacman -Qkk >"/mnt/host/vm/next/package-audit-$variant.log" 2>&1 || true
chroot "$target" /usr/local/sbin/rock5t-kernel status --allow-unmounted-boot >"/mnt/host/vm/next/kernel-status-$variant.json"
[[ -s "$target/usr/lib/firmware/arm/mali/arch10.8/mali_csffw.bin" ]]
[[ -s "$target/usr/lib/firmware/rtl_nic/rtl8125b-2.fw" ]]
[[ ! -e "$target/etc/pacman.d/gnupg" ]]
[[ ! -s "$target/etc/machine-id" ]]
! grep -q '^alarm:' "$target/etc/passwd"
grep -q '^root:!:' "$target/etc/shadow"
! find "$target/etc/ssh" -name 'ssh_host_*' | grep -q .
mkdir -p "/mnt/host/boot-next-$variant"
cp -r --preserve=mode,timestamps "$target/boot/." "/mnt/host/boot-next-$variant/"
find "$target/boot" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
find "$target/var/cache/pacman/pkg" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
find "$target/var/log" -type f -delete
rm -f "$target/root/.bash_history"
rm -rf "$target/root/.gnupg" "$target/root/.ssh"
# No host shares, build scripts, credentials, or virtual-machine configuration ship.
find "$target/mnt" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
mkdir -p "$target/usr/share/rock5t-build"
mkdir -p "$target/usr/share/licenses/rock5t-bootloader"
cp /mnt/host/next-version/rockchip-ddr-LICENSE.TXT "$target/usr/share/licenses/rock5t-bootloader/LICENSE.TXT"
mkdir -p "$target/usr/share/licenses/rock5t-platform"
cp -r /mnt/host/release-repo/LICENSES/. "$target/usr/share/licenses/rock5t-platform/"
cp /mnt/host/research/rock5t-armbian-sources.lock.json "$target/usr/share/rock5t-build/"
cp "/mnt/host/vm/next/packages-$variant-final.txt" "$target/usr/share/rock5t-build/packages.txt"
printf '%s\n' "$variant" >"$target/etc/rock5t/variant"
sync
