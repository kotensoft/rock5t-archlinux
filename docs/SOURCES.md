# Exact sources and redistribution materials

## Linux and board support

The kernel uses Linux 6.18.44 at upstream commit
`1efe5d048a391de3ead2804b2e7f86376c356cc5`, with the Armbian framework snapshot
`fd4ebfd1e107d5b89f7a672c7d609789565753b2`. The framework contains the exact
240 board patches, 21 original driver integration entries and 48 driver patches.
Seven external driver source archives are pinned by full commit and SHA256.
`sources.lock.json` contains exact source archive URLs, sizes and hashes.

The original Linux archive signature was verified against Greg Kroah-Hartman's
key, fingerprint `647F28654894E3BD457199BE38DBBDC86092693E`, retrieved from the
official kernel.org developer-key service. Archive hashes are retained in the
lock. A checksum in a Git repository is not itself a new upstream signature.

`kernel-next/config/baseline.config` is the original authenticated Armbian runtime
configuration (SHA256
`df04c47ef19557272ed2a926f44ec2abea82fcffa334b484589bcbb54c9841a3`).
`landlock.config` is the actual new build configuration. The functional changes
are Landlock enablement, the default LSM list and the distinct local release.
`config-delta.txt` also records toolchain-detection differences.

Matched framework hashes identify a source snapshot consistent with the packaged
components, not a unique attestation of the original upstream builder's checkout.
This distinction is documented in the original provenance report.

## Provide corresponding sources with kernel binaries

Keep the complete pinned source bytes available to recipients, including all
patches, configuration and build/install scripts. For a release download,
publish the matching source bundle alongside the image rather than relying only
on this Git tree or a list of external URLs. The source bundle helper includes:

- Exact Linux source archive, including its complete notices/licenses
- Exact Armbian framework archive, including board/driver patches and tooling
- All seven complete external driver archives, including per-file notices
- Exact U-Boot and TF-A source archives, their complete licenses and the matching
  final bootloader configuration/defconfig/metadata
- This audited repository's source/configuration/build scripts and hashes

The source archives stay outside Git, avoiding large binary Git objects.
To build the bundle from existing verified archives:

```sh
python3 tools/verify-release-tree.py
python3 tools/make-kernel-source-bundle.py \
  --source-root . --output ../rock5t-kernel-corresponding-source.tar
(cd .. && sha256sum -c rock5t-kernel-corresponding-source.tar.sha256)
```

Run the checksum check from the output directory, or otherwise select the path
correctly; the generated sidecar intentionally uses only the archive basename.
If the archives live in another local build workspace, pass its root explicitly.
The helper only reads manifest-listed files and hash-locked source archives. It
does not include `.git`, credentials, logs, VM disks, tool binaries or home files.
A release must verify the uploaded/downloaded archive and preserve the specific
source bundle for that binary version. Recheck the manifest after any source edit.

## Boot stack

The recorded Armbian U-Boot binary uses upstream U-Boot 2026.04 commit
`88dc2788777babfd6322fa655df549a019aa1e69` and TF-A v2.13.0 commit
`c17351450c8a513ca3f30f936e26a71db693a145`. Exact matching framework, patches,
hooks, configuration, DDR identity and license evidence is recorded in
`docs/UBOOT-SOURCE.md`; do not treat the older current-framework reference in
`research/rock5t-armbian-sources.lock.json` as the original binary source.
The source bundle contains the matched open-source boot stack; proprietary DDR
bytes and userspace package source archives are excluded. The exact Rockchip DDR
license is retained separately; see `BOOTLOADER-LICENSE-INSTALL.md`.

## Arch Linux ARM userspace

Installed packages retain their upstream licenses. The final versioned package
inventory and required corresponding source archives must accompany or otherwise
be made available for redistributed GPL-covered userspace components as their
licenses require. This repository's package profiles are not complete package
source archives. Actual installed inventories are recorded (CLI 200, KDE 748); complete userspace
source-material collection remains unresolved as documented separately. Keep `/usr/share/licenses/` in the resulting images.

For exact package metadata, source-recipe groups and per-package material gaps,
see [Userspace source inventory](USERSPACE-SOURCES.md). A recipe hash mismatch
is provenance uncertainty, not an automatic legal conclusion.
