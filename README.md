# ROCK5T Arch Linux ARM community images

CLI and KDE build sources for Radxa ROCK 5T (RK3588), combining Arch Linux ARM
userspace with the Armbian board-support stack. This is a community project,
not an official Arch Linux, Arch Linux ARM, Armbian or Radxa image.

## Current status

Package-completeness correction (2026-10-09): the 2026.10.08 images omitted
`rtkit`, `wireless-regdb` and `iw`. The prior package/firstboot checks did not test
this requirement. Source profiles and release gates are corrected here, but
replacement images have not been built or published. Existing counts and VM
results below describe the old artifacts only. See
[the incident and rebuild requirements](docs/PACKAGE-COMPLETENESS-2026.10.09.md).

- Source implementation, kernel build and the recorded automated checks passed.
- Kernel: `6.18.44-current-rockchip64-landlock1`, with Landlock enabled while
  retaining the matched Armbian Rockchip patches and external drivers.
- Package installation complete: CLI **200 packages**, KDE **748 packages**.
- Root policy audits passed: CLI **28 checks**, KDE **34 checks**.
- CLI image firstboot under an isolated ARM64 QEMU snapshot: **27/27 checks
  passed**, normal shutdown, destroyed snapshot and unchanged source disk SHA256.
- Both CLI and KDE completed disk packaging, compression round-trip verification
  and root/board-initramfs/eMMC software gates. Final artifacts and hashes are
  recorded in [the release summary](evidence/final-release-summary.json).
- Final compressed-image hashes are separate release artifacts. No installation
  images, runtime state or upstream source archives are stored in Git.
- New-version ROCK5T hardware validation: **not performed**. QEMU `virt` results
  do not establish board boot, Wi-Fi, SSH login or a KDE hardware session.

KDE uses Plasma Login Manager and Chromium. First boot creates a local
administrator; images have no usable default login. SSH is off by default and
requires explicit setup. Wi-Fi can be skipped or configured later.

## Documentation

- [中文改动清单](next-version/CHANGELOG.zh-CN.md)
- [Build and reproduction](docs/BUILD.md)
- [Tests and known limits](evidence/VALIDATION.md)
- [eMMC installation and compatibility](emmc-work/README.zh-CN.md)
- [Verified CLI firstboot snapshot test](next-version/firstboot-vm-test/README.md)
- [Source provenance and corresponding-source delivery](docs/SOURCES.md)
- [Userspace source inventory](docs/USERSPACE-SOURCES.md)
- [Third-party notices](NOTICE.md)
- [Release checklist](docs/RELEASE-CHECKLIST.md)
- [Image packaging and verification](packaging-work/README.md)
- [Firstboot and kernel-generation management](overlay-work/README.md)

`profiles/` contains requested package profiles; actual installed versioned lists
are in `evidence/packages-cli-final.txt` and `evidence/packages-kde-final.txt`.
Rolling repository contents mean
profiles alone do not guarantee identical future userspace bytes.

Do not run the guest installation scripts on an installed workstation or board.
They are intended for disposable, explicitly marked build-VM filesystems.
Flash images only after checking the release manifest and backing up the target
media. Flashing overwrites that media.

Source snapshot: handoff 2, including the CPIO directory-root fix and recursive
JSON path-redaction delivery fix. Subsequent compressed-image hash reports are
separate artifacts; users do not need another source download solely for those hashes.
KDE minimal snapshot passed 31/31: firstboot, visible PLM login screen, tty2
login/password-required sudo and policy checks, with normal shutdown and unchanged
source image. Full graphical-session and new-version ROCK5T hardware tests remain
unperformed; emulator DRM/Vulkan warnings are documented.

Final artifact documentation update: [release report](evidence/FINAL-RELEASE.md).
The small addendum updates evidence and documentation; production source code stays
at the reviewed handoff-2 snapshot.
