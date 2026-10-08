# Unprivileged ROCK5T image packaging

`rock5t_image.py` builds complete flashable GPT images from an **offline, cleanly
unmounted ext4 image** and a directory containing the boot files. It uses ordinary
files only: no root privileges, loop devices, mounts, or host filesystem changes.
Do not run while QEMU or another process can write the input root image.

## Stable partition identities

The supplied `cli.ids.json` and `kde.ids.json` contain variant-specific UUIDv5
identities. The root PARTUUID must be inserted into extlinux and `/etc/fstab`
while preparing each root image. The boot PARTUUID is available for `/boot` in
fstab. These identifiers describe GPT partitions, not filesystem UUIDs.

To generate another identity set before preparing an image:

```sh
python3 packaging-work/rock5t_image.py ids \
  --seed archlinux-rock5t-cli-2026-10-07 --output my-cli.ids.json
```

Identical seeds produce identical IDs. Different variants should use different
seeds. This guarantees reproducible partition identities; it does not claim
bit-for-bit reproducibility of arbitrary filesystem inputs or file timestamps.

## Input requirements

- Clean, unmounted, regular ext4 file with a journal and extents, a whole-MiB
  size, and file length exactly equal to the filesystem size.
- Ordinary boot directory containing regular files/directories only. Dereference
  any intended kernel/initramfs/DTB symlinks when staging it. Case-colliding names,
  FAT-unsafe names, and files at or above the FAT32 4 GiB limit are rejected.
- `extlinux/extlinux.conf` with at least one `LABEL`. Every label must have
  `LINUX`, `INITRD`, explicit `FDT`, and `APPEND root=PARTUUID=<root_uuid>`.
  Use absolute paths starting at the FAT partition root. Relative paths are
  interpreted relative to `/extlinux`. Includes and FDT directories are rejected.
- `LINUX` selects an uncompressed ARM64 Linux `Image` (checked for ARM64 magic).
  Every referenced initramfs must exist and be nonempty. This is not an audit of
  its modules, early userspace, or kernel compatibility.
- `FDT` selects a DTB whose root node must identify `Radxa ROCK 5T` /
  `radxa,rock-5t` / `rockchip,rk3588`. The filename is unrestricted; the kernel
  manager's `/rock5t/<release>/board.dtb` is supported. Board identity comes from
  the parsed DTB contents, not its basename.
- The default loader is
  `research/deb-root/usr/lib/linux-u-boot-current-rock-5t/u-boot-rockchip.bin`.
  Its expected RKNS header and safe size are checked. Upstream authenticity must
  already have been checked as part of obtaining this input.

The UUID and filesystem checks do not replace review of `/etc/fstab`, initramfs
contents, installed kernel modules, board firmware, first-boot logic, or security
settings in the root filesystem.

## Build

Run from `rock5t-build` (or use absolute paths):

```sh
python3 packaging-work/rock5t_image.py package \
  --rootfs vm/cli-final.ext4 \
  --boot-dir boot-cli \
  --ids packaging-work/cli.ids.json \
  --output output/archlinux-rock5t-cli.img
```

The output directory must already exist. Existing image, partial, and sidecar
names are never overwritten. `--no-compress` omits xz output. `--bootloader` and
`--tools` can override the discovered loader and downloaded host-tool root.
Only explicit executables beneath that host-tool root are used, with its
`usr/lib/x86_64-linux-gnu` on `LD_LIBRARY_PATH`.

### On-disk layout

| Region | Start | Size |
| --- | ---: | ---: |
| Protective MBR and primary GPT | 0 | through LBA 33 |
| Rockchip combined bootloader | 32 KiB | exact supplied loader size |
| FAT32 `BOOT`, EFI System type | 16 MiB | 1 GiB |
| ext4 `ROOT`, Linux filesystem type | 1040 MiB | exact root image size |
| Backup GPT | end of disk | 33 sectors |

Disk size is rounded up to a MiB after reserving backup GPT space. The loader is
rejected if it would overlap the FAT partition. Root copying preserves sparse
holes without requiring a second full allocation; FAT is built with mtools.
A temporary 1 GiB sparse FAT file is removed after use.
FAT geometry is explicitly set to 64 heads / 32 sectors per track so mkfs.fat
does not round the filesystem down to its default 63-sector track boundary.
The BPB sector count must exactly equal the 1 GiB partition length, and this is
checked immediately after formatting as well as during final verification.

Outputs:

- `.img` and `.img.xz` (unless compression is disabled)
- `.img.sha256` and `.img.xz.sha256`
- `.img.manifest.json`, including UUIDs, geometry, source/content hashes and checks
- `.img.validation.json`, recording verification commands and their outputs

Compression uses xz level 4, two threads, CRC64, and a 1024 MiB compression memory
limit. The generated xz stream is tested before publication under its final name.
Source root identity/timestamps are checked for concurrent modification. Advisory
locking adds protection only against cooperative writers. A failed build may
leave `.partial` or completed files for inspection, and is never reported passed.
Correct the cause and choose a fresh output name rather than blindly overwriting.

## Verify a finished image

```sh
python3 packaging-work/rock5t_image.py verify \
  --image output/archlinux-rock5t-cli.img \
  --manifest output/archlinux-rock5t-cli.img.manifest.json
```

The standalone check independently validates both GPT header/partition-table
CRCs, exact UUIDs/types/geometry, protective MBR, bootloader bytes, root bytes,
FAT32 filesystem geometry, read-only filesystem checks, exact FAT inventory and
file hashes, extlinux references/PARTUUID, DTB identity, and the whole-image hash.
It extracts sparse temporary files for read-only `e2fsck -f -n` and `fsck.fat -n`.
If the unchanged source root is available, add `--rootfs PATH` to avoid extracting
it; a full hash match proves the checked filesystem is the one inside the disk.
Temporary extracts are cleaned on success or exception. Do not confuse software
validation with a real boot test: every manifest explicitly says
`hardware_tested: false`.

Verify downloaded/compressed files separately from the output directory:

```sh
sha256sum -c archlinux-rock5t-cli.img.sha256
sha256sum -c archlinux-rock5t-cli.img.xz.sha256
xz --test archlinux-rock5t-cli.img.xz
```

Checksums detect changes, but unsigned manifests/checksum files are not an
independent provenance/signature guarantee.

## Tests

```sh
cd packaging-work
python3 -m unittest -v test_rock5t_image.py
```

The suite tests stable IDs, sparse range copying, bad extlinux references,
case-colliding/symlink FAT input, wrong DTB model/compatible values despite a valid
`board.dtb` filename, and an actual unprivileged 113 MiB fixture using
64 MiB FAT32 + 32 MiB ext4. The integration fixture uses the real ROCK5T DTB and
loader, a deliberately synthetic ARM64-header kernel and fake initramfs, exercises
both verification paths and xz round-trip hashing, and detects intentional
primary GPT, backup GPT, and bootloader corruption. It is removed after the test
and is never a hardware-bootable image. Production CLI geometry is never reduced.
An additional sparse 1 GiB FAT regression test reproduces the old default-geometry
rounding failure, verifies exactly 2,097,152 sectors with the production formatter,
and checks fsck.fat plus mtools write/read behavior.

## 2026.10.08-landlock1 release (production entrypoint)

The common raw GPT layout is the planned SD/eMMC compatibility approach. Both
CLI and KDE root+boot inputs have passed the eMMC-oriented software audit, but
eMMC whole-disk preparation and hardware acceptance have not been established.
Delivery instructions currently prioritize SD cards. This workflow does not
modify SPI. Existing generic root expansion behavior is unchanged.

Old `cli.ids.json`, `kde.ids.json` and old output files are retained unchanged.
Use `release_image.py` for this release, rather than invoking the low-level packer
with old IDs. Versioned identities are committed under
`releases/2026.10.08-landlock1/{cli,kde}.ids.json`; both the GPT root PARTUUID and
ext4 filesystem UUID must use that variant's new `root_uuid`. Root preparation
must put the same IDs in `/etc/fstab` and `/etc/rock5t/kernel.json` **before**
generating the managed boot menu. IDs are deterministic per variant and release;
clones of the same released image still need offline identity migration if used
together.

The intended artifact paths are:

- `output/2026.10.08-landlock1/archlinux-rock5t-cli-2026.10.08-landlock1.img(.xz)`
- `output/2026.10.08-landlock1/archlinux-rock5t-kde-2026.10.08-landlock1.img(.xz)`

No output/partial/sidecar is overwritten. Keep the full `.img.xz`; splitting never
removes it. Current complete images are for private Library delivery. Public image
publication remains blocked on incomplete userspace source materials; only the
project-owned source is in the current public publication scope. No upload is
performed here.

After the parent build has made clean, offline roots and extracted their actual
boot files, substitute the real paths (and repeat for KDE):

```sh
python3 packaging-work/release_image.py paths --variant cli
python3 packaging-work/release_image.py preflight --variant cli \
  --rootfs <new-offline-cli.ext4> --boot-dir <new-cli-boot>
python3 packaging-work/release_image.py package --variant cli \
  --rootfs <new-offline-cli.ext4> --boot-dir <new-cli-boot>
python3 packaging-work/release_image.py verify --variant cli \
  --rootfs <new-offline-cli.ext4>
```

The additional gate pins the original verified U-Boot SHA256, new payload Image
and ROCK5T DTB, built-in MMC/ext4 kernel configuration, default Landlock, a single initial
kernel generation with matching metadata, version-specific root filesystem UUID,
fstab and kernel.json. It reads the root only through read-only debugfs. It parses
the actual boot initramfs's newc/zstd contents without extracting filesystem
paths, validates normal mkinitcpio hooks (no autodetect), required PCIe PHY,
matching kernel release, and SHA256 of every included module against the tested
kernel payload. The board initramfs must come from the final root build. QEMU
initramfs from `kernel-next` tests is not an acceptable substitute. These checks
are software validation; they do not assert board boot or hardware acceptance.

Packaging uses the fixed production disk geometry and then checks that xz
reproduces the complete raw-image SHA256. `verify` repeats disk verification and
compressed round-trip verification. A completed release manifest contains
`release_preflight` and `compressed_decompressed_sha256_verified: true`.

Prepare delivery only **after** both the image and release verification succeed:

```sh
python3 next-version/delivery-tools/prepare_delivery.py --variant cli
python3 next-version/delivery-tools/prepare_delivery.py --variant kde
```

This makes new `delivery/2026.10.08-landlock1/{cli,kde}/` folders with ordered
`part001`... files no larger than 90 MiB, part and full-image hashes, raw-image
hashes, validation metadata, separate Linux/Windows merge/hash helpers, and concise
Chinese install/recovery notes. All source artifacts are retained. This is a
conservative delivery size, not a claim about a service upload limit. The scripts
never write block devices, change a root image, access user hardware, or upload.

```sh
cd packaging-work
python3 -m unittest -v test_rock5t_image.py test_release_image.py
```

Release fixtures are synthetic, temporary and not bootable hardware images.
PowerShell helpers are statically reviewed when PowerShell is unavailable; the
Linux helpers are executed against split/compressed tiny test fixtures, including
missing/corrupt parts and no-overwrite cases. Report that distinction explicitly.

Delivery JSON reports recursively replace this build directory's absolute prefix
with `$BUILD_ROOT/`, a documented placeholder for the directory containing
`packaging-work`, `output`, and `vm`. Original manifests/logs remain untouched.
Hashes, sizes, relative/device paths and verification outcomes are preserved;
checksums of the exported report files are calculated after redaction.
