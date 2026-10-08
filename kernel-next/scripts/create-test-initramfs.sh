#!/usr/bin/env bash
set -euo pipefail
N=$(cd "$(dirname "$0")/.." && pwd)
T=$(cd "$N/../host-tools/root" && pwd)
R="$N/build/initramfs"
mkdir -p "$R"/{bin,dev,proc,sys,tmp,tests}
cp "$N/arm-extra/usr/bin/busybox" "$R/bin/busybox"
ln -sf busybox "$R/bin/sh"
for app in mount mkdir cat echo chmod timeout poweroff sleep dmesg modprobe grep; do
    ln -sf busybox "$R/bin/$app"
done
export LD_LIBRARY_PATH="$T/usr/lib/x86_64-linux-gnu"
"$T/usr/bin/aarch64-linux-gnu-gcc" -O2 -Wall -Wextra -static \
  -I"$N/build/headers/usr/include" "$N/scripts/landlock-smoke.c" \
  -o "$R/tests/landlock-smoke"
cp "$N/build/selftests/"* "$R/tests/"
cat > "$R/test-init" <<'EOF'
#!/bin/sh
export PATH=/bin
mount -t devtmpfs devtmpfs /dev
mount -t proc proc /proc
mount -t sysfs sys /sys
mount -t tmpfs tmpfs /tmp
chmod 1777 /tmp
mount -t securityfs securityfs /sys/kernel/security
mkdir -p /sys/fs/cgroup
mount -t cgroup2 none /sys/fs/cgroup
echo +cpu > /sys/fs/cgroup/cgroup.subtree_control
mkdir /sys/fs/cgroup/landlock-smoke
echo QEMU_TEST_CONTEXT_ARM64_VIRT_NO_ROCK5T_HARDWARE
if grep -q 'test.expected_landlock=disabled' /proc/cmdline; then
    /tests/landlock-smoke --expect-disabled
    echo NEGATIVE_CONTROL_EXIT=$?
    poweroff -f
fi
/tests/landlock-smoke
echo SMOKE_EXIT=$?
cd /tests
for test in base_test scoped_test scoped_signal_test scoped_abstract_unix_test ptrace_test; do
    echo UPSTREAM_SELFTEST_BEGIN=$test
    timeout 180 ./$test
    echo UPSTREAM_SELFTEST_EXIT=$test:$?
done
echo UPSTREAM_SELFTEST_BEGIN=fs_test_layout0_layout1
timeout 180 ./fs_test -f layout0 -f layout1
echo UPSTREAM_SELFTEST_EXIT=fs_test_layout0_layout1:$?
echo UPSTREAM_SELFTEST_BEGIN=net_test_selected
timeout 180 ./net_test -f mini -f ipv4_tcp -f tcp_layers
echo UPSTREAM_SELFTEST_EXIT=net_test_selected:$?
echo ALL_QEMU_TESTS_FINISHED
poweroff -f
EOF
cat > "$R/init" <<'EOF'
#!/bin/sh
# pivot_root cannot replace the special initramfs rootfs mount.
export PATH=/bin
mkdir /newroot
mount -t tmpfs -o size=512m tmpfs /newroot
/bin/busybox cp -a /bin /tests /newroot/
mkdir -p /newroot/dev /newroot/proc /newroot/sys /newroot/tmp
/bin/busybox cp -a /test-init /newroot/init
echo QEMU_TEST_SWITCH_ROOT_TO_TMPFS
exec /bin/busybox switch_root /newroot /init
EOF
chmod +x "$R/init" "$R/test-init"
(cd "$R" && find . -print0 | "$N/host-extra/usr/bin/cpio" --null -o --format=newc --owner=0:0) \
  | gzip -n > "$N/build/landlock-tests.cpio.gz"
