# Release checks

The source snapshot can be reviewed independently of any installation image.
Do not turn a pending check into a pass without its specific evidence.

## Source publication

- [ ] Run `python3 tools/verify-release-tree.py` and review every finding.
- [ ] Run the selected automated tests from `docs/BUILD.md` on the final snapshot.
- [ ] Preserve LICENSE, per-component notices, exact source/configuration locks.
- [ ] Review local modifications to image scripts made during the final build,
      synchronize the final safe versions, and regenerate source checksums.
- [ ] Verify the published remote commit equals the locally reviewed commit.

## Binary image publication

- [x] Install intended CLI/KDE packages and pass 28/34 root-policy checks.
- [x] Complete CLI disk packaging/verification and actual firstboot snapshot test (27/27).
- [x] Pass CLI/KDE board-initramfs and eMMC root-and-boot software preflight.
- [x] Complete KDE disk packaging/compression verification and record final image checksums.
- [ ] Verify remote publication/download availability separately; local checks do not establish upload.
- [ ] Record final `pacman -Q`, package source origins and signatures, input hashes,
      output hashes and image validation results. Retain package license files.
- [ ] Verify no default usable accounts, keys, credentials, machine identity,
      network profiles, build mounts or personal logs remain in either rootfs.
- [ ] Independently verify GPT, bootloader, FAT, ext4, extlinux, initramfs, DTB,
      kernel-generation/module inventory and uncompressed/compressed hashes.
- [ ] Publish the complete matching kernel corresponding-source bundle next to
      binary downloads; verify the downloaded source bundle SHA256 and contents.
- [x] Match exact U-Boot component identifiers and DDR bytes; record the matching
      TF-A recipe/version. See `UBOOT-SOURCE.md` for the boundaries of this evidence.
- [ ] Preserve and publish U-Boot/TF-A required source,
      patches, configuration and notices. Do not substitute a current unrelated
      source snapshot for the version used by the binary.
- [ ] Provide corresponding sources required by the licenses of redistributed
      userspace packages. Package names or current upstream links alone are not
      an archival substitute for the exact version's required source.
- [ ] State hardware tests accurately. New-version board validation remains
      unperformed unless a separate documented hardware test occurs.

A successful QEMU run, source publication or checksum does not mark the binary
image checks complete. The source-fetch instructions are useful for reproduction;
they are not a claim that an external download host will retain files forever.

- [x] Complete bounded KDE snapshot (31/31), PLM login-screen visibility and safe teardown.
- [ ] Full graphical-session and physical-hardware acceptance remain outside this test scope.
