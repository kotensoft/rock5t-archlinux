#!/bin/bash
set -euo pipefail
grep -qw 'rock5t.builder=1' /proc/cmdline || { echo 'Only finalize disposable build-VM targets' >&2; exit 1; }
variant=${1:?cli or kde}; target=/mnt/$variant
case "$variant" in cli|kde) ;; *) exit 2;; esac
mountpoint -q "$target" || { echo 'Target must be a mounted image filesystem'; exit 1; }
[[ $(findmnt -n -o SOURCE "$target") == /dev/vd[b-z] ]] || exit 1
[[ ! -e "$target/var/lib/pacman/db.lck" ]] || exit 1
for p in dev proc sys run; do mkdir -p "$target/$p"; mount --rbind "/$p" "$target/$p"; mount --make-rslave "$target/$p"; done
cleanup() { for p in run sys proc dev; do umount -R "$target/$p" || true; done; }
trap cleanup EXIT
chroot "$target" pacman -R --noconfirm linux-aarch64
find "$target/boot" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
chmod 750 "$target/etc/sudoers.d"
chown 0:50 "$target/var/games"
python3 /mnt/host/overlay-work/prepare-rootfs.py --root "$target" --variant "$variant"
python3 - "$target" "$variant" <<'PY'
import json,pathlib,sys
r=pathlib.Path(sys.argv[1]);v=sys.argv[2];ids=json.loads(pathlib.Path('/mnt/host/packaging-work/releases/2026.10.08-landlock1/'+v+'.ids.json').read_text())
cmd='root=PARTUUID='+ids['root_uuid']+' rootfstype=ext4 rw rootwait console=ttyS2,1500000n8 console=tty1 rt_group_sched=0'
(r/'etc/rock5t/kernel.json').write_text(json.dumps({'cmdline':cmd})+'\n')
(r/'etc/fstab').write_text(f"PARTUUID={ids['root_uuid']} / ext4 defaults,noatime 0 1\nPARTUUID={ids['boot_uuid']} /boot vfat defaults,umask=0077 0 2\n")
(r/'etc/issue').write_text('ROCK5T community image: Arch Linux ARM + Armbian 6.18.44\nHardware acceptance pending. No default credentials.\n')
PY
chmod 750 "$target/etc/sudoers.d"
systemctl --root "$target" disable dhcpcd.service systemd-networkd.service systemd-resolved.service 2>/dev/null || true
systemctl --root "$target" enable systemd-timesyncd.service
if [[ $variant == kde ]]; then systemctl --root "$target" enable bluetooth.service; fi
rm -f "$target/etc/resolv.conf"; ln -s /run/NetworkManager/resolv.conf "$target/etc/resolv.conf"
touch -d @1791388800 "$target/usr/lib/clock-epoch"
chroot "$target" /usr/local/sbin/rock5t-expand-firmware
mapfile -t releases < <(find "$target/usr/lib/rock5t-kernel" -mindepth 1 -maxdepth 1 -type d -printf '%f\n')
((${#releases[@]} == 1)) || { echo "Select a single initial kernel payload" >&2; exit 1; }
KREL=${releases[0]}
grep -qx 'CONFIG_SECURITY_LANDLOCK=y' "$target/usr/lib/rock5t-kernel/$KREL/config"
chroot "$target" /usr/local/sbin/rock5t-kernel activate --allow-unmounted-boot --release "$KREL"
chroot "$target" visudo -cf /etc/sudoers
units=(rock5t-firstboot@tty1.service rock5t-firstboot@ttyS2.service rock5t-provisioned.target)
if [[ $variant == kde ]]; then units+=(plasmalogin.service); fi
systemd-analyze --root="$target" --man=no verify "${units[@]}" >"/mnt/host/vm/next/systemd-$variant-verify.log" 2>&1
chroot "$target" pacman -Q >"/mnt/host/vm/next/packages-$variant-final.txt"
python3 /mnt/host/scripts/package_contract.py --root "$target" --variant "$variant" \
    --manifest "/mnt/host/vm/next/packages-$variant-final.txt" \
    >"/mnt/host/vm/next/package-contract-$variant.json"
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
