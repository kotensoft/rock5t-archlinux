# Matched Armbian kernel inputs

Verified on 2026-10-08.

The official Armbian framework commit below matches every checked kernel component identifier from the authenticated package.

https://github.com/armbian/build/tree/fd4ebfd1e107d5b89f7a672c7d609789565753b2

Commit time: 2026-08-18 03:59:50 UTC.
Package changelog time: 2026-08-18 04:32:26 UTC.
The commit is the last main-branch commit before that package time in the retrieved GitHub history.
The framework VERSION file reads `26.08.0-trunk`.
The package version `26.8.3` results from separate package reversioning.
No `v26.8.3` release tag appeared in the official remote's advertised tags.

## Matched component hashes

- Framework Bash: `4990fb4ba983d439`
- Driver Bash: `539705d8ef732820`
- Driver patch directory: `ceaab8e69a899eb1`
- Combined reported driver hash: `539705d8_ceaab8e6`
- Rockchip 6.18 patch directory: `d9e569eab50e60b3`
- Source configuration: `40fcc37a0d6cf7d4`
- Default configuration hooks: `2153b201d2f3d096`
- Packaging variables: `c22207b66dc5dd57157df2cd7b9c20559b2ed8ac44b9c3c3b9704002c06b8921`
- Empty extension-hook body input: `01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b`

The first six hashes use the original `calculate_hash_for_files` algorithm.
It hashes each relative filename and SHA256, then hashes the resulting ordered lines.
The compiler helper list was checked against the official GitHub directory at the same commit.
Run `verify-component-hashes.sh FRAMEWORK_DIRECTORY` to repeat the checks.

The configuration hook hash independently matches with these inputs:

- `ARCH=arm64`
- `BRANCH=current`
- `KERNEL_MAJOR_MINOR=6.18`
- `KERNEL_BTF=yes`
- Original core configuration hooks, with no custom configuration hooks

Run `check-default-config-hooks.sh` to reproduce this result.

The packaging-variable hash matches the default arm64 values: `install`, `Image`, empty, `Image`, empty.
Those values correspond to `KERNEL_INSTALL_TYPE`, `KERNEL_IMAGE_TYPE`, `KERNEL_EXTRA_TARGETS`, `NAME_KERNEL`, and `SRC_LOADADDR`.
The empty extension-hook body input produces prefix `01ba`, matching the package identifier.
The complete normalized hook changes are in `default-config-hook-modifications.txt`.

## Source interpretation

These checks establish a matching framework source snapshot for the packaged kernel's recorded component identifiers.
They do not prove that the original build worker checked out this unique whole-repository Git commit.
Unrelated framework changes can preserve all kernel component hashes.
No original build-worker checkout attestation was found.

The authenticated package names upstream kernel commit `1efe5d048a391de3ead2804b2e7f86376c356cc5`, Linux 6.18.44.
Use that upstream release with this snapshot's complete driver integration and Rockchip patch processing.
Use the authenticated package's final configuration as the baseline for a minimally changed rebuild.
A rebuilt binary need not be byte-identical because toolchains, build paths, timestamps, and requested options can differ.

## Driver-skip limitation

`KERNEL_DRIVERS_SKIP` influences only the driver patch cache filename in this snapshot.
It does not enter the reported driver hash or the kernel artifact version.
Consequently, the reported driver hash alone cannot prove the original skip list was empty.
The default ROCK5T/current board and family configuration do not add any skipped drivers.
The RK3588 family adds `driver_rtl8723cs` only for its legacy branch.
Preserve all 21 entries in the original driver harness order for the current branch.
Each original function applies its own kernel-version and family conditions.
Seven pinned external source snapshots apply to rockchip64/6.18.
They come from six repository origins.
All are pinned by full commit IDs in the original Armbian source.

## Evidence

- `commits-aug18.json`: official GitHub commit chronology.
- `compilation-tree-aug18.json`: official helper directory listing.
- `hash-files-aug18.sh`: original hash implementation.
- `artifact-kernel-aug18.sh`: original artifact identifier calculation.
- `fd4ebfd1/`: raw official files used for initial small-file checks.
- `original-driver-references.tsv`: source coordinates extracted from the original driver script.
- `original-driver-order.txt`: exact original driver order.
- `driver-download-hashes.tsv`: exact download origins and SHA256 values.

Official chronology URL:
https://github.com/armbian/build/commits/main/?since=2026-08-16&until=2026-08-19

Official archive URL:
https://codeload.github.com/armbian/build/tar.gz/fd4ebfd1e107d5b89f7a672c7d609789565753b2

## Driver integration result

The original 21 driver harness entries completed successfully.
The run applied 48 original patches and copied the seven pinned source snapshots.
The local driver-integrated commit is `e409d1e7fd3c8f852c89eee7866538f1331df4e5`.
That commit changes 4,563 files with 4,580,243 insertions.

Three hunks use fuzz level 2 under Armbian's original patch behavior.
Two hunks add the RTL8703BS constant and table entry in `drivers/bluetooth/btrtl.c`.
One hunk adds the RTL8723CS source line inside `drivers/staging/Kconfig`.
Their resulting placement was inspected and matches the intended context.
No patch failed in the completed run.

`driver-sources.lock.json` records all external source URLs, full commit IDs, archive sizes, and SHA256 values.
`../scripts/prepare-drivers.sh` reproduces fetching and integration without modifying the original framework helpers.
`../logs/driver-integration.log` records the successful run.

The initial run stopped on non-UTF-8 text in an original patch.
The helper's path parser now uses a byte-preserving encoding.
Only that partial run's generated changes were reset before the successful run.
