# Reproducing the source and builds

Run host commands from this repository root on a disposable x86_64 Linux build
host. The recorded kernel was built using Debian GCC 14.2.0-19 (AArch64 cross),
GNU binutils 2.44 and pahole 1.30. Do not reuse an installed ROCK5T as the builder.
A source-reproducible recipe is provided; identical compiler, paths, timestamps,
userspace repository snapshots and filesystem metadata are additionally needed
for byte-identical artifacts. Byte-for-byte image reproducibility is not claimed.

## Prepare exact kernel sources

1. Review `sources.lock.json`. Fetch missing source archives, or verify an
   already materialized source bundle:

   ```sh
   python3 tools/fetch-kernel-sources.py --fetch
   # Offline verification only:
   python3 tools/fetch-kernel-sources.py
   ```

2. Provide Python 3.12+, Git, bash, curl, dpkg (version comparison), patch,
   tar/xz, make, cross GCC/binutils, host GCC, bison, flex, m4, OpenSSL headers,
   libelf headers, pahole, rsync, kmod and zstd from the build host's official
   package repositories. Prepare the patcher's isolated Python environment:

   ```sh
   python3 -m venv kernel-next/venv
   kernel-next/venv/bin/python -m pip install -r kernel-next/requirements.txt
   ```

3. In a fresh checkout, integrate all pinned drivers and all Armbian board
   patches, then verify the resulting Git tree identity:

   ```sh
   tools/prepare-kernel-source.sh
   ```

   Expected tree: `7b3a45f61573390bc15beecf01c6324d5170c687`.
   The recipe fails closed if the tree differs. It will not overwrite an
   existing Linux source directory. A local commit ID need not match because
   commit metadata differs; the complete tracked source tree must match.
   The new convenience wrapper has syntax/hash tests; clean source assembly
   through that wrapper has not yet been independently repeated.

4. Build in a separate output directory with the provided final configuration:

   ```sh
   kernel-next/scripts/kernel-make-portable.sh olddefconfig
   diff -u kernel-next/config/landlock.config kernel-next/build/board/.config
   kernel-next/scripts/kernel-make-portable.sh -j8 Image modules dtbs
   ```

   Review configuration changes introduced by your toolchain; never ignore a
   lost board driver or Landlock/LSM setting. The original successful build
   wrapper `kernel-next/scripts/kernel-make.sh` is also preserved. It expects
   extracted Debian packages in `host-tools/root` and `kernel-next/host-extra`.
   The portable wrapper uses installed tools and is not a byte-reproducibility
   assertion about the original binaries.

5. The original staging and QEMU selftest scripts are retained in
   `kernel-next/scripts/`. They expect the original extracted-tool layout,
   static ARM64 BusyBox and libcap files under `kernel-next/arm-extra`, and
   the original authenticated Armbian binaries under `research/deb-root`.
   Review their documented dependencies before running them. QEMU `virt`
   tests are not a substitute for ROCK5T testing.

## CLI and KDE image assembly

`profiles/cli.packages` is the common base for both variants;
`profiles/kde.packages` adds the desktop. `rtkit`, `wireless-regdb` and `iw` are
explicit common requirements. The installer checks all requested package names
with `pacman -Q`; `scripts/package_contract.py` checks finalized roots against
both profiles, pacman local metadata, and required package files. The offline
release preflight independently reads the embedded inventory and pacman database
from ext4 and records the result in the release manifest. Package omission fails
before packaging. Historical 2026.10.08 manifests are expected to fail this gate.
The build flow uses the signed Arch Linux ARM rootfs, an isolated ARM64 QEMU
builder, the next-version kernel package and an offline image packager.

- `scripts/create-builder-initramfs.sh`, `scripts/start-next-vm.sh` and
  `scripts/next-guest-runner.sh`: the current next-kernel build VM, using the
  compiled Landlock kernel and a disposable guest job queue.
- `scripts/next-guest-bootstrap.sh`: bootstrap/package-resolution preparation.
- `scripts/start-vm.sh`: the older generic-kernel disposable VM route; adds
  `rock5t.builder=1` to its command line. Only files under its build workspace
  are shared into that VM. Proxy environment, if configured, stays ignored.
  The scripts use QEMU SLIRP defaults `10.0.2.15` (guest), `10.0.2.2`
  (gateway) and `10.0.2.3` (DNS). These are emulator configuration values,
  not a device discovery result. Adapt the guest and QEMU network together
  if choosing another subnet. Never copy `vm/proxy.env` or raw bootstrap
  logs into a source release or installation image.
- `scripts/profile-packages.sh`: package installation gate and CLI/KDE selection.
- `scripts/make-kernel-package.sh`: package the explicit new kernel payload
  only after configuration/provenance validation.
- `scripts/finalize-target.sh` and `overlay-work/prepare-rootfs.py`: firstboot
  policy, identity/credential cleanup, initramfs/kernel-generation activation.
- `packaging-work/rock5t_image.py`: offline GPT/FAT/ext4 assembly and verification.

CLI/KDE package installation and root-policy audits have completed; the actual
200/748 package lists and 28/34 passed policy checks are in `evidence/`.
The CLI disk has passed packaging/verification and its actual firstboot snapshot
test (27/27 checks). Both variants passed root/board-initramfs/eMMC software gates.
Both CLI and KDE disk packaging/compression verification completed. Final hashes
are in `evidence/releases/2026.10.08-landlock1/SHA256SUMS`; the full reports are
under the same directory. This evidence addendum does not change production code.
The current scripts preserve the actual staged workflow, but this snapshot is
not yet a tested one-command full-image rebuild from a fresh machine. A rootfs
URL containing `latest` and unlocked rolling package resolution are not immutable
inputs. Release manifests must include their exact hashes and resolved versions.
The older Armbian binary lock is retained for the bootloader, baseline config
and regression reference; the new image kernel is built from the pinned sources.

## Safe source-level tests

These tests do not change host services or use physical disks:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_package_contract.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s overlay-work/tests -v
PYTHONDONTWRITEBYTECODE=1 python3 next-version/test_kernel_package_gate.py
(cd packaging-work && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_rock5t_image.UnitTests)
python3 tools/verify-release-tree.py
```

OpenSSH parser tests need installed `sshd` and `ssh-keygen`; they create only
disposable test keys and never start a listener. The PLM binary-fixture test needs `ROCK5T_TEST_PACKAGES` pointing to the verified
package cache; it is explicitly skipped in a source-only checkout. Optional real-kernel retention
tests are skipped unless their documented explicit payload paths are provided.
Packaging integration tests additionally require downloaded host tools and the
real reference ROCK5T DTB/bootloader, all deliberately absent from Git. Run them
only as documented in `packaging-work/README.md`; they create temporary synthetic
image files, not installation images or physical-device writes.
