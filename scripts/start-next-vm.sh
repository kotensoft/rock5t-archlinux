#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Optional builder-only proxy environment; never copied to a target root.
python3 - <<'PROXY'
import os, pathlib, shlex
lines=[]
for key in ('http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY'):
    value=os.environ.get(key) or os.environ.get(key.upper())
    if value:
        lines.append('export '+key+'='+shlex.quote(value.replace('127.0.0.1','10.0.2.2').replace('localhost','10.0.2.2')))
p=pathlib.Path('vm/proxy.env');p.write_text('\n'.join(lines)+'\n');p.chmod(0o600)
PROXY
T=$PWD/host-tools/root
export LD_LIBRARY_PATH=$T/usr/lib/x86_64-linux-gnu
args=(-M virt -cpu cortex-a72 -accel tcg -m 3072 -smp 6 -display none -serial file:vm/next/serial.log -monitor pipe:vm/next/control/monitor -kernel kernel-next/payload/boot/Image -initrd vm/next/builder-initramfs.cpio.gz -append 'console=ttyAMA0 rdinit=/init loglevel=3 rock5t.builder=1 rt_group_sched=0' -drive if=none,id=root,file=vm/rootfs-next.ext4,format=raw,discard=unmap,detect-zeroes=unmap -device virtio-blk-pci,drive=root -netdev user,id=net0 -device virtio-net-pci,netdev=net0,romfile= -virtfs local,path="$PWD",mount_tag=hostshare,security_model=none,id=hostshare -no-reboot)
for name in cli kde; do
 if [[ -f vm/$name-final.ext4 ]]; then args+=(-drive "if=none,id=$name,file=vm/$name-final.ext4,format=raw,discard=unmap,detect-zeroes=unmap" -device "virtio-blk-pci,drive=$name"); fi
done
exec "$T/usr/bin/qemu-system-aarch64" "${args[@]}"
