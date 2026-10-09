# Package omission: verified cause and correction

The published 2026.10.08-landlock1 CLI and KDE package inventories contain none
of `rtkit`, `wireless-regdb` or `iw`. These were required components. Their omission
is a release defect; passing the historical checks did not establish completeness.

## Evidence and cause

- Both direct profiles omitted all three names. The common CLI profile feeds the
  CLI image and the base cloned for KDE.
- The cached build repository metadata identifies `rtkit` as a PipeWire optional
  dependency, rather than a required dependency. NetworkManager does not require
  `iw` or `wireless-regdb`. Installing the desktop/network packages did not ensure
  the omitted packages were installed. `wireless-regdb` itself depends on `iw`.
- The original root audit checked only the KDE additions against its direct
  profile, not the common CLI profile and not these explicit requirements.
- The offline release gate checked disk/boot/kernel identity, not the installed
  package contract. The CLI 27-check and KDE 31-check firstboot collectors lacked
  package-presence, regulatory database, and RTKit activation checks.
- A new read-only traversal of the original KDE `.img` found 748 package database
  entries, matching all names in its embedded inventory, with all three absent.
  Its embedded inventory exactly matches `evidence/packages-kde-final.txt`, SHA256
  `4683da8c0ebebe224fc8c6c729ecb0d7617d725acac4b44ff264483031938dea`.
- The independently recomputed original KDE whole-image SHA256 is
  `fc05165c08764ef8000251d40dc99b2b7fd4cb8cbcdeb592314e2194bb34e195`, matching the
  released manifest. This establishes that the omission predates any private
  installation customization. The CLI conclusion is based on its retained
  published package inventory; its compressed image was not reinspected here.

Missing RTKit is consistent with D-Bus `ServiceUnknown`. This audit does not
establish that the separate Wi-Fi driver error `-16` is caused by missing
`wireless-regdb`; physical driver initialization still needs independent testing.

The machine-readable original-image audit is retained in
[`evidence/package-omission-audit-2026.10.09.json`](../evidence/package-omission-audit-2026.10.09.json).

## Source changes

1. Add all three packages to the shared CLI profile. KDE installation explicitly
   includes the common profile and checks every requested package after install.
2. Add a read-only package contract with a hard requirement for all three direct
   common entries, CLI-plus-KDE coverage, strict versioned manifest parsing,
   matching pacman local descriptions, and nonempty required payload files.
   Local database directory versions preserve any epoch.
3. Enforce this contract in both finalization paths and the root policy audit.
4. Enforce it again against offline ext4 before image packaging. Record requested
   versions and inventory SHA256 in release preflight evidence. An old manifest
   lacking this evidence cannot pass the corrected release verification gate.
5. Extend both firstboot collectors with all three package queries, executable
   `iw`, signed regulatory database file presence, and RTKit D-Bus activation.
6. Preserve historical evidence unchanged; it must not be relabeled as a pass
   for corrected artifacts.

The files expected by the contract agree with the official Arch package file
lists for [rtkit](https://archlinux.org/packages/extra/x86_64/rtkit/files/) and
[wireless-regdb](https://archlinux.org/packages/core/any/wireless-regdb/files/).
The corrected build must still verify the actual signed ARM package payloads.

## Firstboot and the 8 GiB root are separate issues

The public image intentionally contains distribution public keyrings without
the builder's local trust key. The local-console firstboot wizard runs
`pacman-key --init` and `pacman-key --populate archlinuxarm archlinux` before it
commits `/var/lib/rock5t/provisioned`. Failure prevents normal completion.
The recorded CLI and KDE QEMU firstboot evidence confirms trust initialization.

An existing provisioned marker skips the entire wizard and unlocks SSH, gettys
and the desktop. Any private provisioning path that writes that marker must
perform equivalent trust initialization itself. This audit did not inspect
private customization or establish what it changed.

Root expansion is opt-in, default No. The original KDE root is 8 GiB, while CLI
is 4 GiB. The recorded tests explicitly declined growth. An unchanged 8 GiB KDE
root therefore does not by itself establish a public-image failure. Real eMMC
growth and driver behavior are not proven by QEMU firstboot evidence.

## Required corrected-release work

A separately versioned corrected image release is recommended. Do not overwrite
the original release assets or reuse their completion claims. Before publication:

- Choose a new version and new partition identities consistently in finalization
  and packaging; the historical defaults remain unchanged in this source patch.
- Install signed current required packages in disposable build targets; record
  exact resolved dependencies, signatures, licenses and matching sources.
- Run full root, package, boot, disk, and compression gates on both new artifacts.
- Rerun the expanded firstboot suites, then separately record physical board
  audio/Wi-Fi/eMMC validation with its actual results and limits.
- Refresh package inventories, source provenance, checksums and release notes.

This source-only correction does not rebuild, flash, upload or publish any image.
