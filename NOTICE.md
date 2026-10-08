# Licensing and upstream attribution

The project build scripts and documentation in this repository are distributed
under GNU GPL version 2 (`LICENSE`), except where a file or component states a
different license. Third-party components retain their own notices and licenses;
this repository does not relicense them or imply endorsement.

- Linux: Linus Torvalds and many contributors. The exact upstream `COPYING` file
  and `LICENSES/` directory are preserved under `LICENSES/`. Linux is GPL-2.0-only
  with the Linux syscall note and the per-file licenses identified upstream.
- Armbian build framework, board patches and integrations: Armbian contributors.
  Its upstream `LICENSE` is preserved unchanged as `LICENSES/Armbian-LICENSE`.
- External Realtek/Unisoc wireless drivers: respective upstream authors. Exact
  repositories, commits and archive hashes are listed in
  `kernel-next/provenance/driver-sources.lock.json`. The standalone COPYING/LICENSE
  files present in those archives are copied under `LICENSES/drivers/`. Other
  drivers carry notices in source-file headers; the complete pinned source
  archives preserve those notices. Absence of a root LICENSE file is not a
  permission to discard the per-file notices.
- Arch Linux ARM and all installed userspace packages retain their individual
  licenses. The image's installed package list and `/usr/share/licenses/` must be
  preserved. No single license statement here covers the entire installation image.
- OpenSSH parser fixtures retain the original upstream text and file headers.
  Their exact package provenance is documented alongside the fixtures.
- U-Boot license texts and TF-A main/component license inventory are retained
  under `LICENSES/U-Boot/` and `LICENSES/TF-A/`. Rockchip DDR firmware retains
  its distinct `LICENSES/Rockchip-DDR-LICENSE.TXT` notice. These have separate
  source and licensing requirements. See `docs/SOURCES.md` and the boot-stack provenance
  report before publishing any image containing them.

Upstream projects:
https://www.kernel.org/
https://github.com/armbian/build
https://archlinuxarm.org/
https://source.denx.de/u-boot/u-boot
https://github.com/ARM-software/arm-trusted-firmware
https://github.com/armbian/rkbin

This source tree contains no private credentials, signed-in account state,
installation-image payloads or copied home-directory contents. Names such as
`alice`, `vmcheck` and `alarm` appearing in tests are synthetic examples or the public
factory account. QEMU user-network addresses are fixed emulator defaults, not
captured device or local-network addresses.
