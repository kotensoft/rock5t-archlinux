# ROCK5T image provisioning and retained kernel generations

This directory is an integration overlay, not a flashable image. All changes made
while developing it were confined to this directory. Device boot, HDMI, UART,
networking, firstboot interaction and root growth still require real hardware QA.

## Runtime packages

Install `bash coreutils util-linux shadow sudo openssh python systemd
networkmanager e2fsprogs kmod mkinitcpio zstd pacman gnupg archlinuxarm-keyring
archlinux-keyring`. Install `cloud-guest-utils` to offer
partition expansion. KDE additionally needs plasma-meta, Plasma Login Manager, Chromium and the Plasma/Wayland
session packages. This overlay does not select a graphics driver or compositor.
The script's `NetworkManager.service` spelling is the systemd unit; Arch's package
name is lowercase `networkmanager`.

## Apply after package installation

Run on an **offline image tree**, not a running root filesystem:

```sh
python3 prepare-rootfs.py --root /absolute/path/to/rootfs --variant cli
# or --variant kde
```

This copies `rootfs/`, enables the two setup consoles, selects the default target,
removes the `alarm` account/group/home, discards root's original password hash and
locks root, removes account backup files, scrubs machine-id/SSH host keys/random
seed, deletes `/etc/pacman.d/gnupg` (including the builder's local secret package-trust key), removes passwordless sudo rules, and disables enabled SSH service/socket
links. Root and alarm have no usable default password. A new administrator is
created locally, added to wheel, and must supply a password for sudo. Keep this
step last so later package scripts do not put reusable identity material back in
the image. Run the final image's own `visudo -c` and `sshd -t` after provisioning
(or run `sshd -T` for policy inspection when image keys have been scrubbed).

If provisioning inside the build VM, copy the overlay but **do not start the
firstboot services**. Enable the same links, then scrub the identity only after
all operations that might regenerate it are complete. Do not run `pacman-key --init`
or `--populate` in the target after final preparation; keep the package-provided
public keyring files under `/usr/share/pacman/keyrings/` intact. `prepare-rootfs.py` refuses
`--root /` deliberately; use it against the offline exported image tree.

### Firstboot behavior

- `tty1` and `ttyS2` both show setup. UART is 1500000 baud, 8N1.
- Each waits for Enter; a single flock serializes account provisioning. The unused
  console polls for completion and then gives way to normal login.
- The normal virtual/serial getty templates are gated; no login shell is offered before provisioning. Root remains locked; `alarm` is gone.
- `passwd` reads directly from the local terminal. Passwords are not stored in a
  firstboot config or written to shell arguments/logs.
- User creation is resumable after interruption. A pending username is retained,
  and the password is set again before commit.
- Plasma Login Manager, gettys and sshd require the final provisioned marker. PLM also waits for both setup services to exit. KDE starts PLM, never SDDM or a conflicting tty1 getty; CLI starts tty1 getty.
- NetworkManager may be started during an explicitly chosen Wi-Fi phase after account/trust initialization, using /run/rock5t-network-ready. This temporary gate never unlocks desktop or SSH. Interrupted uncommitted setup closes the temporary network gate.
- Unique machine ID is created by systemd on real first boot; host keys are made
  by `ssh-keygen -A` during setup. SSH defaults disabled/public-key-only. The local administrator explicitly chooses current access, boot enablement and optional password login; remote root/alarm remain denied. See docs/NETWORK-SSH-NEXT.md.
- Package trust is initialized locally using `pacman-key --init`, then
  `pacman-key --populate archlinuxarm archlinux`. Both public keyring packages must
  already be installed. This does not use the network. No builder-generated
  private pacman key is shipped. Missing keyrings or command failure prevent the
  provisioned marker; the pending user remains available for a setup retry.
- Optional growth uses `growpart` and `resize2fs`, only for a plain ext4 root on
  the physically last partition. LUKS/LVM/RAID and non-ext4 are rejected. Failure
  leaves setup usable and prints a retry command; it never formats a filesystem.
- A 3.3 V UART adapter must be used. UART electrical compatibility and actual
  board pinout are outside this overlay and must be verified before attachment.

## Compressed firmware compatibility

The selected Armbian 6.18.44 kernel lacks `CONFIG_FW_LOADER_COMPRESS`; the image
must contain uncompressed firmware. `rock5t-expand-firmware` creates companions
for every `.xz`/`.zst` file below `/usr/lib/firmware`. It preserves the original
package files, reproduces aliases as uncompressed symlinks, and records outputs
in a private bookkeeping manifest. Run it before the initial initramfs build:

```sh
rock5t-expand-firmware
# Or from the builder against an offline target:
python3 rootfs/usr/local/sbin/rock5t-expand-firmware --root /mnt/cli
```

The `90-rock5t-firmware-expand.hook` repeats this after firmware package installs,
upgrades and removals, before the `99-...` kernel activation hook. Each decompression
uses a same-directory temporary file and commits only after successful decoding.
Locally modified/untracked raw files are never overwritten when their contents
differ; package-owned raw files take precedence. Obsolete generated companions
are removed only if their content still matches the helper's recorded output.
Preparation preserves this manifest for future upgrades. Symlink form is preserved,
including aliases such as `.bin.xz -> actual.bin.xz` becoming `.bin -> actual.bin`.
This is per-file fail-safe replacement, not an atomic transaction over all firmware.
An interrupted/failed command leaves a pending marker that blocks subsequent
kernel activation until a successful firmware-expansion retry.

Explicitly verify these required raw files in the built image:

- `/usr/lib/firmware/arm/mali/arch10.8/mali_csffw.bin` (Panthor)
- `/usr/lib/firmware/rtl_nic/rtl8125b-2.fw` (RTL8125)

The generic initramfs additionally forces `phy_rockchip_snps_pcie3`, which is a
module in this kernel and is needed early for an NVMe root. The kernel's actual
module/firmware availability must still be checked during image integration.

## Kernel package contract

`linux-rock5t` is a normal pacman package. Its payload owns only:

```text
/usr/lib/rock5t-kernel/<exact-uname-r>/
  Image                         # uncompressed ARM64 Image
  dtbs/rockchip/rk3588-rock-5t.dtb
  modules/                      # contents of lib/modules/<exact-uname-r>/
    kernel/...ko[.xz|.zst]
    modules.dep
    modules.builtin ...
  manifest.json
```

Do not put `/boot` files or runtime `/usr/lib/modules/<release>` in the package.
Do not ship `build` or `source` symlinks in `modules/`. Generate `modules.dep` with
`depmod` for that exact release when preparing the package payload. Run:

```sh
python3 packaging/make-manifest.py path/to/<exact-uname-r>
```

`packaging/PKGBUILD.in` is a buildable template after replacing the four marked
values and archiving the release directory. Preserve the verified source, full
package version, source commit/package checksums and license separately in the
image build provenance. This template does not download or authenticate a kernel.
Every change to kernel or module payload requires a distinct actual `uname -r`.
Changing only pacman's `pkgrel` is insufficient. Upstream same-release rebuilds
must be rebuilt with a distinct LOCALVERSION before they can coexist safely.

### Initial build in the ARM64 VM

1. Install `linux-rock5t` and dependencies before installing the overlay's pacman
   hooks. Otherwise the post-transaction hook correctly refuses an unmounted
   `/boot` during image construction.
2. Copy the overlay scripts, hooks and mkinitcpio config.
3. Write `/etc/rock5t/kernel.json` with the final root partition GUID:

```json
{"cmdline":"root=PARTUUID=<ROOT-PARTITION-GUID> rootfstype=ext4 rw rootwait console=ttyS2,1500000n8 console=tty1"}
```

4. Ensure any stock extlinux config is explicitly removed/replaced by the builder.
   The manager refuses to silently overwrite an unmanaged boot config.
5. Expand compressed firmware with `rock5t-expand-firmware`, then run in the build VM:

```sh
rock5t-kernel activate --allow-unmounted-boot --release <exact-uname-r>
```

This runs target `depmod` and `mkinitcpio`, with a generic configuration that omits
build-host `autodetect`. `--allow-unmounted-boot` is an explicit image-assembly
override; normal pacman hooks do not use it. For offline host assembly with an
already-generated matching ARM64 initramfs instead:

```sh
python3 rootfs/usr/local/sbin/rock5t-kernel activate \
  --root /absolute/path/to/rootfs --allow-unmounted-boot \
  --release <exact-uname-r> --initramfs /path/to/matching-initramfs.img
```

The offline path does not execute target binaries. The builder is responsible for
ensuring the supplied initramfs matches the kernel; a nonempty file check is not a
bootability test. Export `/boot` onto the FAT32 boot partition root. Paths in
extlinux.conf are `/rock5t/<release>/...`, relative to that partition. Keep rootfs
`/boot` an empty mount point and add the correct FAT mount to `/etc/fstab`.

### Upgrades and manual recovery

- The pre-transaction hook validates mounted `/boot`, current/previous checksums,
  and retained modules. An invalid current state aborts a kernel upgrade/removal.
- Pacman installs the new payload without owning or deleting active boot files
  or runtime modules. A failed pacman transaction therefore leaves the previously
  active runtime generation intact even if its old package payload was removed.
- The post hook validates the complete new payload, copies modules to a new
  unique release path, runs depmod/mkinitcpio, flushes a staged boot generation,
  then changes extlinux.conf last using same-directory replacement.
- The new menu has current and previous entries. On failure before the commit,
  the old selection is preserved. `extlinux.conf.previous` holds the prior menu.
- `sudo rock5t-kernel status` checks retained generations.
- `sudo rock5t-kernel rollback` swaps the current and previous menu selections.
  It does not downgrade the pacman package or roll back root filesystem data.
- There is **no automatic failed-boot detection**. Choose the previous entry in
  the U-Boot menu when necessary. Bootloader support and UART keyboard/menu input
  must be validated on ROCK5T hardware.
- There is **no automatic deletion of old generations**. This intentionally avoids
  removing the running kernel or a needed recovery image. Out-of-space fails
  safely before switching. Administrators may remove unreferenced old generation
  and module pairs only after checking current, previous and `uname -r`.
- Do not run another kernel manager, generic module-cleanup script, or ad hoc
  `depmod`/module install over retained releases. Checksums detect modifications.
  Installing an out-of-tree module requires a deliberate new image/kernel release
  under this strict immutable-generation design.
- Immutable here describes updater behavior, not filesystem write protection.
  Root can modify files; the system does not provide Secure Boot or a signed
  measured-boot trust chain.

FAT32 does not provide journaled, cross-filesystem transactions. Commit-last and
fsync reduce exposure to interruption but cannot guarantee recovery from arbitrary
power cuts, controller write-cache loss or media corruption. This is a retained
manual recovery design, not a verified A/B firmware scheme. The original flash
image should be kept as an external recovery copy.

## Verification performed

Run `PYTHONDONTWRITEBYTECODE=1 python3 tests/test_overlay.py` from this directory.
The 29 tests exercise successful activation, previous-image/module retention,
pacman-payload deletion, failed initramfs generation/retry, immutable release
checks, corrupt files, symlinks, unmounted/full boot, unmanaged boot configuration,
manual rollback, identity/default-account cleanup, private pacman key scrubbing/public-ring retention,
key initialization ordering and strict console allowlisting, CLI/KDE configuration and firmware expansion/update/failure/symlink/ownership behavior.
`bash -n` passes for both shell scripts; Python compilation passes. Host
`systemd-analyze verify` cannot initialize because its `/run/systemd` is read-only;
run it inside the ARM64 build VM instead. ShellCheck is not installed in this
workspace. Real tty authentication, concurrent setup and expansion are not
executed by these unit tests.

Historical release-validation boundaries (not scheduled or reopened by this code-only task; real hardware work needs separate authorization):

- `systemd-analyze verify` the installed setup template/target and normal units;
  `visudo -c`; inspect `sshd -T` and the explicitly selected SSH state.
- Boot each image on ROCK5T, with local keyboard/HDMI and UART independently.
  For generic QEMU validation, provision a temporary test-only tty1 console. Do
  not widen the shipped tty1/ttyS2 allowlist to accept ttyAMA0, pseudo-terminals,
  SSH or an arbitrary console. Discard test-only console changes before imaging.
- Start setup on both consoles, interrupt after user creation, resume, and ensure
  there is never a pre-provisioned getty, desktop or network login.
- Check two separately flashed devices generate distinct machine IDs and host
  keys and pacman local private trust keys, no root/alarm password works, and sudo requires the new user's password.
- Opt into root growth on larger SD/eMMC/NVMe, then verify filesystem size.
- Upgrade using a distinct release; test the previous menu entry and rollback.
- Exercise a failing mkinitcpio run and nearly-full FAT partition in a disposable
  image, verifying the previous generation still boots.

## Primary references

- [Pacman hook ordering, AbortOnFail and post-transaction failure semantics](https://man.archlinux.org/man/alpm-hooks.5.en)
- [mkinitcpio kernel, config and generated-image options](https://man.archlinux.org/man/mkinitcpio.8.en)
- [systemd terminal execution options](https://man.archlinux.org/man/systemd.exec.5.en)
- [systemd unit conditions and ordering](https://man.archlinux.org/man/systemd.unit.5.en)
- [Pacman local trust-key initialization and public keyring population](https://man.archlinux.org/man/pacman-key.8.en)
- [Machine ID setup](https://man.archlinux.org/man/systemd-machine-id-setup.1.en)
- [growpart behavior](https://man.archlinux.org/man/growpart.1.en)
- [U-Boot extlinux configuration](https://docs.u-boot.org/en/latest/develop/distro.html)
