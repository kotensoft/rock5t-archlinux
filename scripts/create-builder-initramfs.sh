#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
R=$PWD/vm/next/initramfs
KREL=6.18.44-current-rockchip64-landlock1
mkdir -p "$R"/{bin,dev,proc,sys,newroot,lib/modules}
cp kernel-next/arm-extra/usr/bin/busybox "$R/bin/"
for app in sh mount mkdir modprobe sleep switch_root; do ln -sf busybox "$R/bin/$app"; done
cp -a "kernel-next/payload/usr/lib/modules/$KREL" "$R/lib/modules/"
cat > "$R/init" <<'INIT'
#!/bin/sh
export PATH=/bin
mount -t devtmpfs devtmpfs /dev
mount -t proc proc /proc
mount -t sysfs sys /sys
modprobe virtio_pci
modprobe virtio_blk
modprobe virtio_net
modprobe 9pnet_virtio
modprobe 9p
sleep 1
mount -t ext4 /dev/vda /newroot || exec sh
mount --move /dev /newroot/dev
mount --move /proc /newroot/proc
mount --move /sys /newroot/sys
mkdir -p /newroot/mnt/host
mount -t 9p -o trans=virtio,version=9p2000.L hostshare /newroot/mnt/host || exec sh
exec switch_root /newroot /bin/bash /mnt/host/scripts/next-guest-runner.sh
INIT
chmod +x "$R/init"
(cd "$R"; find . -print0 | ../../../kernel-next/host-extra/usr/bin/cpio --null -o -H newc --owner=0:0) | gzip -1n > vm/next/builder-initramfs.cpio.gz
