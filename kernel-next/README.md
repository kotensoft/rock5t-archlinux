# ROCK5T Landlock kernel verification

This workspace builds a local test kernel. It does not install a kernel or create an installation image.

## Sources

- Linux 6.18.44: upstream commit `1efe5d048a391de3ead2804b2e7f86376c356cc5`.
- Armbian: commit `fd4ebfd1e107d5b89f7a672c7d609789565753b2`.
- Every recorded source, driver, patch, configuration, and hook identifier matches the authenticated Armbian 26.8.3 package.
- The Linux tarball has a valid Greg Kroah-Hartman signature. The signing key comes from official kernel.org HTTPS.
- `provenance/ARMBIAN-ORIGINAL-SOURCE-PROVENANCE.md` explains the matching evidence and remaining provenance limits.

The build keeps all 21 original driver integration entries, seven pinned external sources, and 48 driver patches.
The original Armbian patcher applies 240 board patches and integrates DTS files, overlays, and Makefiles.
The generated ROCK5T DTB exactly matches the original package's DTB.

## Configuration

The baseline is the authenticated package's final configuration.
Its SHA256 is `df04c47ef19557272ed2a926f44ec2abea82fcffa334b484589bcbb54c9841a3`.

Functional changes:

- Enable `CONFIG_SECURITY_LANDLOCK=y`.
- Add `landlock` before the existing `CONFIG_LSM` entries.
- Use release `6.18.44-current-rockchip64-landlock1` to isolate this build.

Rust toolchain detection metadata differs because this host lacks Rust. The original kernel does not enable Rust.
`provenance/config-delta.txt` records every configuration difference.
DWARF5, BTF, board drivers, and `CONFIG_RT_GROUP_SCHED=y` remain enabled.

The tested RT policy uses `rt_group_sched=0` with runtime 950000 and period 1000000 microseconds.
The build does not disable RT throttling or change another RT security setting.

## Reproduction

The `scripts` directory contains the commands used for source integration, compilation, staging, and QEMU testing.
Use the pinned archives and their recorded SHA256 values.

1. Extract the Linux archive into `linux-6.18.44` and create a local Git baseline.
2. Run `scripts/prepare-drivers.sh integrate` on the clean baseline. Commit the result.
3. Write that local commit to `provenance/driver-source-local-commit.txt`.
4. Run `scripts/apply-board-patches.sh`. Commit the patched tree.
5. Record `git rev-parse HEAD^{tree}` in `provenance/patched-source-tree-hash.txt`.
6. Copy the baseline configuration to `build/board/.config`. Apply the two Landlock configuration changes.
7. Run `scripts/kernel-make.sh olddefconfig`. Check the full configuration delta.
8. Run `scripts/kernel-make.sh -j8 Image modules dtbs`. Record its status in `logs/kernel-build.exit`.
9. Run `scripts/build-selftests.sh` and `scripts/create-test-initramfs.sh`.
   Run `scripts/run-qemu-negative-control.sh`, saving output to `logs/qemu-original-negative.log`.
10. Run `scripts/run-qemu-tests.sh`, saving output to `logs/qemu-landlock.log`.
11. Run `scripts/stage-payload.sh`. Inspect `payload/provenance.json` before using the payload elsewhere.

Host dependencies come from the authenticated Debian trixie repository or pinned Python packages from PyPI.
`host-extra` supplements the existing `../host-tools/root` cross compiler and QEMU tools.
`arm-extra` contains Debian arm64 static BusyBox and libcap development files for the test initramfs.
No root privileges, proot, or host kernel modifications are used.

## Test scope

QEMU uses the ARM64 `virt` machine with TCG. It does not emulate ROCK5T peripherals.
The old official kernel passes a negative control: Landlock is absent and its syscall returns `ENOSYS`.
The new test checks the running release, default active LSM list, ABI, and unprivileged filesystem enforcement.
It checks the unchanged RT budget and unprivileged SCHED_RR inside a non-root CPU cgroup.
It also runs upstream base, scoping, signal, abstract Unix socket, and ptrace selftests.
Selected upstream filesystem and network fixtures run without requiring emulated board devices.

The final QEMU run passes the enforcement/RT smoke test and all 173 selected upstream tests, with zero skips.
The active list is `capability,landlock,yama,apparmor`. The reported Landlock ABI is 7.
An initial run has two `pivot_root` failures because the special initramfs rootfs cannot be replaced by `pivot_root`.
The test bootstrap now switches to a normal tmpfs root before testing. The same two tests then pass without modification.
`logs/qemu-landlock-initramfs-root.log` preserves the initial result. `logs/qemu-landlock.log` contains the corrected full run.

Compilation and QEMU results cannot establish hardware boot, peripheral operation, or video decoding.
No new-version ROCK5T hardware boot result is included.

`pacman-smoke/RESULT.md` records an additional actual ALARM pacman test.
Its default Landlock and seccomp sandbox starts successfully as download UID/GID 970.
Three real repository databases download successfully from an official direct mirror.
The remaining repository reaches the unchanged low-speed timeout and is not retried.
A bounded core-only test then downloads `filesystem` and its normal `iana-etc` dependency successfully.
Pacman verifies both package signatures as valid and fully trusted, with default sandbox and timeout settings preserved.

## Local payload

- `boot/Image`
- `boot/config-6.18.44-current-rockchip64-landlock1`
- `boot/System.map-6.18.44-current-rockchip64-landlock1`
- `boot/dtbs/rockchip/rk3588-rock-5t.dtb`, plus the complete generated DTB and overlay set
- `usr/lib/modules/6.18.44-current-rockchip64-landlock1`
- `provenance.json`, with source commits, input hashes, configuration delta, test results, and output hashes

The module inventory check fails if any of the original 3577 module paths disappear.
The original DTB installer mishandles an absolute overlay README path with an out-of-tree build.
`stage-dtbs.py` copies every generated `dtbs-list` entry to the intended relative path, including that original README.
This staging correction does not alter kernel sources, compiled DTBs, or overlays.
This staging layout is a build output, not an installation or release authorization.
