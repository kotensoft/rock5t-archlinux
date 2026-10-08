#!/bin/bash
set -eu
cd "$(dirname "$0")/.."
python3 - <<'PY'
import os,shlex,pathlib
lines=[]
for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
 v=os.environ.get(k) or os.environ.get(k.upper())
 if v: lines.append('export '+k+'='+shlex.quote(v.replace('127.0.0.1','10.0.2.2').replace('localhost','10.0.2.2')))
p=pathlib.Path('vm/proxy.env');p.write_text('\n'.join(lines)+'\n');p.chmod(0o600)
PY
T=$PWD/host-tools/root
export LD_LIBRARY_PATH=$T/usr/lib/x86_64-linux-gnu
args=(-M virt -cpu cortex-a72 -accel tcg -m 3072 -smp 4 -nographic -kernel vm/Image -append 'console=ttyAMA0 root=/dev/vda rw init=/bin/bash loglevel=3 rock5t.builder=1' -drive if=none,id=root,file=vm/rootfs.ext4,format=raw,discard=unmap,detect-zeroes=unmap -device virtio-blk-pci,drive=root -netdev user,id=net0 -device virtio-net-pci,netdev=net0,romfile= -virtfs local,path="$PWD",mount_tag=hostshare,security_model=none,id=hostshare -no-reboot)
if [[ -f vm/kde-final.ext4 && ! -f vm/cli-final.ext4 ]]; then echo 'Both target images are required together' >&2; exit 1; fi
for name in cli kde; do
 if [[ -f vm/$name-final.ext4 ]]; then args+=(-drive "if=none,id=$name,file=vm/$name-final.ext4,format=raw,discard=unmap,detect-zeroes=unmap" -device "virtio-blk-pci,drive=$name"); fi
done
exec "$T/usr/bin/qemu-system-aarch64" "${args[@]}"
