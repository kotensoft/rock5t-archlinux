# ROCK5T prebuilt U-Boot source review

Verified 2026-10-08. Source/metadata verification only; no U-Boot rebuild or hardware boot validation is claimed.

## Result

The complete Armbian build snapshot at commit `fd4ebfd1e107d5b89f7a672c7d609789565753b2` reproduces **all five recorded U-Boot component hashes** for the existing authenticated ROCK5T 26.8.3 package:

| Recorded input | Recomputed value | Result |
|---|---|---|
| U-Boot + TF-A patch inputs | `05fe3b9a63ca850e` | Match |
| Extension hook source | `45e42e29ed80425e56623d5a2d7aeedef8b3405461e91a1082187f5fa70b9045` | Match |
| U-Boot/TF-A function bodies | `5d42cc02cb77c2c4c35986b8efd4c6d8f4ef677f7e20c7e81ccb6bacadea2aa8` | Match |
| Normalized build/package variables | `9e871aa8124fe599364e1c44a7e73941f77ffc9aab50bc27a46c47ad47e98601` | Match |
| U-Boot framework Bash files | `5da4413f38e29074` | Match |

The verifier produces `2026.04-S88dc-P05fe-H50cb-V9e87-B5da4`. The package adds the independent reversion suffix `-R448a` and Debian package version `26.8.3`.

This establishes a matching source-input snapshot. It does not prove the original build worker checked out that unique whole-repository commit: the snapshot is dated after the binary and unchanged relevant components can appear in many commits. No original worker attestation was found.

The entire 76,480-byte DDR firmware file was also found **byte-for-byte** in both packaged images, stronger evidence than a filename/version-string match:

- `u-boot-rockchip.bin`: byte offset 2,048
- `u-boot-rockchip-spi.bin`: byte offset 34,816

The current source-reference snapshot `1613ba6961bf378b150285887d6c2a2e497fd9cd` is unsuitable as an exact replacement: patches, function bodies, and framework Bash hashes differ.

## Authenticated package and retained configuration

Package:

`linux-u-boot-rock-5t-current_26.8.3_arm64__2026.04-S88dc-P05fe-H50cb-V9e87-B5da4-R448a.deb`

[Official package URL](https://apt.armbian.com/pool/main/l/linux-u-boot-rock-5t-current/linux-u-boot-rock-5t-current_26.8.3_arm64__2026.04-S88dc-P05fe-H50cb-V9e87-B5da4-R448a.deb)

SHA256: `347222b02dd3a9d105e268de9f1453a51db9de50e53291c7dab39e27e1692f56`

The existing `research/rock5t-armbian-sources.lock.json` records repository signature verification and the package checksum. This review reused that authenticated package and checked its embedded metadata/configuration; it did not redo repository signature verification.

Retain these package files as build inputs/evidence:

| File under `/usr/lib/linux-u-boot-current-rock-5t/` | SHA256 |
|---|---|
| `u-boot-config-target-1` | `5f1789e136ba9d067ac5b7ffe96a7cf4ad805c5698a2d51fb1d753a6f4e82ad5` |
| `u-boot-defconfig-target-1` | `7cf4091ef6a649f31283a1adc3ba018299939f4b22c705a996190e6b23d55bc2` |
| `u-boot-metadata-target-1.sh` | `bb3095630983a335d0468b75313fd4abee42245b93a19b2cf5d624cf92011741` |
| `u-boot-metadata.sh` | `d98bcbdf64920331f2c55cff8488dbbfba9a23b34fcc3d57bdbfaaa44a4f2cea` |
| `u-boot-rockchip.bin` | `bde61feff0227b7616f57cce507ee7764290274b41c09499e988f2ff1753e337` |
| `u-boot-rockchip-spi.bin` | `cbac9f0a54274daf73cd9aacc84a9249ed146c35594dd8f048dc3bb22136f3a7` |

Package changelog: 2026-07-24 17:36:21 UTC. Embedded U-Boot build time: 2026-07-24 17:35:57 UTC. Embedded TF-A build time: 2026-07-24 17:35:16. Embedded compiler string: `aarch64-linux-gnu-gcc (Debian 14.2.0-19) 14.2.0`.

The board recipe intentionally uses `rock5b-rk3588_defconfig`; the packaged configuration has `CONFIG_DEFAULT_DEVICE_TREE="rockchip/rk3588-rock-5b"` and `CONFIG_DEFAULT_FDT_FILE="rockchip/rk3588-rock-5b.dtb"`. The package's image/kernel reference is separately `rockchip/rk3588-rock-5t.dtb`. Preserve these observed values rather than silently replacing the U-Boot defconfig as part of source preparation. Hardware behavior has not been tested in this review.

The ROCK5T configuration hook agrees with the final configuration: SPI environment enabled, automatic sector size enabled, environment overwrite enabled, environment size `0x20000`, environment offset `0xc00000`, boot delay 1.

## Exact source retrieval coordinates

### U-Boot

- Upstream commit: `88dc2788777babfd6322fa655df549a019aa1e69`
- Tag: `v2026.04`; [official tag page](https://github.com/u-boot/u-boot/releases/tag/v2026.04) resolves to the same commit.
- Repository: `https://github.com/u-boot/u-boot.git`
- Pinned source archive: https://codeload.github.com/u-boot/u-boot/tar.gz/88dc2788777babfd6322fa655df549a019aa1e69
- Saved file: `next-version/u-boot-88dc2788777babfd6322fa655df549a019aa1e69.tar.gz`
- Size: 45,534,314 bytes
- SHA256: `c9858cd5fdc0204e72d5c2d4f0e185883fe627a5901f91c165ddecd787899117`
- Archive read validation passed: 40,462 entries. Its Makefile and `Licenses/README` match independently retrieved files at the pinned commit.
- Preserve the full `Licenses/` directory and per-file notices. [Licenses/README](https://github.com/u-boot/u-boot/blob/88dc2788777babfd6322fa655df549a019aa1e69/Licenses/README) identifies GPL version 2 with individual-file exceptions/options; this is not a basis to relabel every bundled component GPL.

### Arm Trusted Firmware (TF-A)

- Upstream commit: `c17351450c8a513ca3f30f936e26a71db693a145`
- Tag: `v2.13.0`; [official tag page](https://github.com/ARM-software/arm-trusted-firmware/releases/tag/v2.13.0) resolves to the same commit. The pinned Makefile reports 2.13.0.
- Repository: `https://github.com/ARM-software/arm-trusted-firmware`
- Pinned source archive: https://codeload.github.com/ARM-software/arm-trusted-firmware/tar.gz/c17351450c8a513ca3f30f936e26a71db693a145
- Saved file: `next-version/arm-trusted-firmware-c17351450c8a513ca3f30f936e26a71db693a145.tar.gz`
- Size: 10,672,549 bytes
- SHA256: `e1e3339d85eb4d8b04f26e2a9f8e43691bd0ed053b9d97276a44b336ea1234b1`
- Archive read validation passed: 6,364 entries. Its Makefile and `docs/license.rst` match independently retrieved pinned files.
- Main license and third-party component inventory: [docs/license.rst](https://github.com/ARM-software/arm-trusted-firmware/blob/c17351450c8a513ca3f30f936e26a71db693a145/docs/license.rst). Main license is BSD-3-Clause; preserve the listed third-party notices as well.

The matching Armbian recipe uses `ATF_COMPILE=yes`, `ATFPATCHDIR=atf-rockchip64/v2.13`, `M0_CROSS_COMPILE=arm-linux-gnueabi- PLAT=rk3588 bl31`, and output `build/rk3588/release/bl31/bl31.elf`. The matched `compile_atf` function supplies `ENABLE_BACKTRACE=0`, default `LOG_LEVEL=40`, and `BUILD_STRING=armbian`, plus its compiler flags and conditional linker-flag probe. The embedded `v2.13.0(release):armbian` string agrees. No TF-A rebuild or byte-identical comparison was performed.

`rk3588_bl31_v1.48.elf` is a recipe fallback blob, **not** the BL31 embedded in these images. Do not present that fallback as corresponding TF-A source or as the binary used here.

### Complete matching Armbian framework

- Commit: `fd4ebfd1e107d5b89f7a672c7d609789565753b2`
- [Official snapshot](https://github.com/armbian/build/tree/fd4ebfd1e107d5b89f7a672c7d609789565753b2)
- Pinned archive: https://codeload.github.com/armbian/build/tar.gz/fd4ebfd1e107d5b89f7a672c7d609789565753b2
- Existing saved archive: `kernel-next/armbian-fd4ebfd1.tar.gz`
- SHA256: `2159f01d54e26d0517fb1a7f15b1024b6c320e95c0423045aec661fc0fbf27b9`
- Compared extracted snapshot against the archive: all 8,755 regular files and 90 symlink targets match.

Keep the complete archive, including source patching machinery, YAML overlay instructions, configuration, extensions, scripts, and notices. The patch hash includes files for other boards too, so a hand-pruned patch directory does not reproduce the package hash.

## Hash algorithm and repeatable verification

Saved verifier: `tools/verify-uboot-source.sh`.

Run from the project root:

```sh
bash tools/verify-uboot-source.sh \
  kernel-next/build-fd4ebfd1e107d5b89f7a672c7d609789565753b2
```

This only loads declarations, prepares recipe variables, dumps function source, and computes hashes. It does not invoke compilation, patching, fetching, flashing, or source-modifying hooks. It passes the package's recorded U-Boot commit to a local stub for the original version calculator's network lookup; therefore it verifies framework component hashes, not the authenticity of the upstream commit independently. The upstream commit is independently supported by the package metadata and official source archive/tag.

The verifier was executed successfully against fd4ebfd1. A negative control against 1613ba failed as expected:

- Patches: `4bcd23e580850d60`
- Functions: `4ddf3c54de4e79048070af7bfb2e967104643d6cac66aa270600f5fcbc55832a`
- Framework Bash: `56a7970830a19b4a`
- Hooks and variables remain equal

The implementation used is the matched snapshot's `lib/functions/general/hash-files.sh` and `lib/functions/artifacts/artifact-uboot.sh`:

1. File hashes: collect files with `find -L`; strip the source-root prefix; sort relative names using `LC_ALL=C sort -h`; run SHA256 on each file. SHA256 the resulting ordered `sha256sum` lines, including filenames and a final newline; keep the first 16 hexadecimal characters.
2. Patch hash: all files below `patch/u-boot/v2026.04` and `patch/atf/atf-rockchip64/v2.13`, together with any corresponding user-patch trees. The matching test has no user patches. U-Boot patches alone produce `b430f8f619f85323`, which is deliberately not the package's combined hash.
3. Framework Bash hash: `lib/functions/compilation/uboot*.sh` plus `lib/functions/compilation/packages/utils-dpkgdeb.sh`, using the same file-hash algorithm.
4. Function hash: existing functions in the original ordered list are dumped via `declare -f`, joined by spaces, terminated by a newline, and hashed with full SHA256. The list includes U-Boot postprocessing/platform writers and `compile_atf`; family-specific missing functions are skipped.
5. Hook hash: the original extension source-dump wrapper emits its begin/end markers and normalized function bodies for the seven hook points. SHA256 covers this text. Both globally enabled U-Boot compatibility extensions must be included.
6. Variable hash: the original ordered variable values are joined by spaces, source-root path occurrences are removed, a newline is appended, and full SHA256 is calculated. Empty `UBOOT_DEBUGGING` and `SRC_EXTLINUX` values reproduce this artifact; explicitly setting these to `no` changes the hash. The output metadata uses a later display/default value `UBOOT_EXTLINUX_PREFER="no"`.
7. The hook SHA256 and function SHA256 are joined with a space/newline and hashed again. Its `50cb` prefix is the package's `H50cb` component.

The exact matching extension hook implementations are:

- `pre_config_uboot_target__fix_binman_pkg_resources`
- `pre_config_uboot_target__fix_pylibfdt_swig`
- `pre_config_uboot_target__warn_modern_hosts`
- `post_config_uboot_target__extra_configs_for_rock5t_mainline_environment_in_spi`
- `check_uboot_produced_binary_file__check_vendor_uboot_for_0_byte_dtb`

The two compatibility extensions are enabled in `lib/functions/configuration/main-config.sh`. Omitting them produces a different hook hash even though the board/family hooks are present.

## DDR binary identity and exact upstream license

The byte-identical file is:

`rk35/rk3588_ddr_lp4_2112MHz_lp5_2400MHz_v1.20_20250926.bin`

Pinned download: https://raw.githubusercontent.com/armbian/rkbin/1d3c61008fa823936ae7a59615393f8294b64456/rk35/rk3588_ddr_lp4_2112MHz_lp5_2400MHz_v1.20_20250926.bin

- Size: 76,480 bytes
- SHA256: `4986b4711fee4a32f716fcf6e3491291f43193ded98caff7cff3e2f081b506e6`
- Retrieval was independently rechecked against the existing local blob and embedded bytes.
- The original framework follows the moving rkbin `master` branch. The recorded artifact hash does not pin or hash that repository revision. The commit above is an exact byte-matching retrieval coordinate, not an attestation of the original rkbin checkout.

The relevant file at that exact repository snapshot is uppercase `LICENSE.TXT`:

- [Pinned license](https://github.com/armbian/rkbin/blob/1d3c61008fa823936ae7a59615393f8294b64456/LICENSE.TXT)
- Raw URL: https://raw.githubusercontent.com/armbian/rkbin/1d3c61008fa823936ae7a59615393f8294b64456/LICENSE.TXT
- Saved verbatim: `LICENSES/Rockchip-DDR-LICENSE.TXT`
- Size: 6,585 bytes
- SHA256: `0b37e1522c36cf4579c45dfb138798c3cb5665fcf6302b95377179fbed38e35c`

Concrete terms to preserve in release preparation: binary copying/distribution is permitted subject to the agreement; distribution must accompany Rockchip platforms and the agreement; standalone distribution, modification, reverse engineering, and removing notices are restricted; the blob must not be subjected to open-source licensing terms. Do not place it in a generic GPL source bundle or public source repository as source code. Include its exact license alongside the board-image bootloader materials. This is an inventory of the pinned notice, not a conclusion about every possible release arrangement.

The current `rockchip-linux/rkbin` repository has a materially different license notice. That notice was not substituted for the agreement accompanying the selected Armbian fork snapshot.

No DDR source code was found or claimed. The DDR binary is proprietary firmware with separately documented terms.

## Remaining evidence and publication checklist

1. Archive the pinned U-Boot and TF-A sources, the complete matched framework, the original final `.config`/defconfig and metadata, and this verifier. Preserve their upstream notices and checksums.
2. Carry the exact DDR agreement in the ROCK5T image/materials. Keep the proprietary blob separate from open-source source packages. The original Debian package contains U-Boot's `Licenses/README` as `/usr/lib/u-boot/LICENSE`; it does not include the DDR agreement or the TF-A license document in its listed payload.
3. Do not claim a proven original build-worker checkout: only the relevant component identifiers match. The package's July build predates fd4ebfd1's August snapshot.
4. Do not claim bit-for-bit rebuilt U-Boot/TF-A: no rebuild was requested or performed. Compiler identity is observable, but a complete original toolchain/container/dependency lock and original build logs are absent.
5. The final packaged U-Boot config is retained but has not been regenerated from pristine source in this review. Source input hashes do not cover every possible out-of-band modification or toolchain behavior.
6. A patch-directory hash proves matching patch-input contents, not a independently replayed patch application. The full framework preserves patch selection, overlays, hook code and compile rules for a later authorized rebuild.
7. TF-A is tied to the selected tag/commit by the matching recipe, the public tag mapping, and its embedded version/build string. A direct rebuilt BL31 comparison remains unperformed.
8. No hardware boot test was performed. Source provenance and board boot validation are separate checks.

All source archives and the license were retrieved from official project repositories over HTTPS. GitHub's unauthenticated API was rate-limited during some lookups; official public repository/tag pages, pinned raw files and pinned codeload archives supplied the completed checks. No authenticated fallback or credentials were used.
