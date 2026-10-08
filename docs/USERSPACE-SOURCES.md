# Userspace source and license inventory

An installation image redistributes many independent packages. The Linux and
boot-stack source bundle does not cover the complete Arch Linux ARM userspace.
The files in this section help identify exact source-material gaps; they do not
certify legal compliance or make the complete sources available by themselves.

## Inventory exact installed versions

Run from a build workspace with the verified package cache and final `pacman -Q`
outputs. The tool reads package metadata and computes archive hashes; it never
installs packages, executes package scripts or changes a root filesystem.

```sh
python3 release-repo/tools/inventory-userspace-sources.py \
  --cache arch-packages \
  --repository-db vm/core.db --repository-db vm/extra.db \
  --repository-db vm/alarm.db --repository-db vm/aur.db \
  --variant cli=vm/next/packages-cli-final.txt \
  --variant kde=vm/next/packages-kde-final.txt \
  --stage final \
  --route-evidence next-version/research/userspace-sources/source-route-evidence.json \
  --output next-version/userspace-sources-final.json \
  --csv next-version/userspace-sources-final.csv \
  --summary next-version/userspace-sources-final.md
```

Adjust the script prefix to `tools/` if working directly in a source checkout.
For a provisional plan, use `--planned-url-list label=package-urls.txt` and
`--stage provisional`. Planned packages are explicitly distinguished from actual
installed versions. A final run rejects prospective URL lists. Cache packages
that do not match an installed or planned exact version are not silently selected.

The inventory records only public package-source fields: package name/base,
version, architecture, declared licenses, upstream URL, archive hash, expected
PKGBUILD SHA256 from `.BUILDINFO`, build-tool version and source-evidence gaps.
It intentionally omits packager identity, build paths, environment, installed
build-dependency lists, logs and all local trust/key material. It hashes detached
signature files when present but does not claim to repeat signature verification.
For an inherited package absent from the binary cache, optional `--repository-db`
inputs can supply exact-version name/base/license/URL metadata. These records stay
explicitly labeled as repository-index-only; no `.BUILDINFO` or PKGBUILD digest
is invented, and index metadata is not a substitute for binary authentication.

The same source recipe can generate several split packages; `source_recipe_groups`
groups the exact package base/version/PKGBUILD-hash combinations to avoid duplicate
source collection. Missing package-base metadata remains explicitly unresolved.
The optional `--route-evidence` file attaches reviewed partial source findings,
separating actual material gaps from original-build provenance gaps. Every listed
local material file is rechecked by size/SHA256. These records are marked partial;
the tool never turns partial retrieval into a complete-source certification.

## What a complete source review still needs

For each relevant exact source recipe:

1. Establish the build recipe and relevant modifications used for the distributed
   program. A PKGBUILD SHA256 matching `.BUILDINFO` is strong exact-byte provenance
   evidence when available. A mismatch is not by itself proof of missing required
   corresponding source or a legal bar to distribution; examine actual code,
   patches, build/install scripts and any explained formatting/transform changes.
   An upstream Arch recipe with a matching version is a candidate, not automatic
   proof of the ARM recipe. Account for relevant ALARM overrides and transforms.
2. Preserve every auxiliary recipe file, patch, install/build helper, required
   configuration and relevant license notice at the same recipe revision.
3. Resolve every source entry, architecture-specific source array, pinned VCS
   commit and submodule to exact source bytes. An upstream homepage is not a
   source archive. Record archive hashes and signature checks where applicable.
4. Check package-internal third-party components. The top-level `.PKGINFO` license
   field is not a complete license inventory; a nominal BSD/MIT package can
   bundle components carrying additional obligations.
5. Retain and provide the source materials required by each license in the
   applicable manner when distributing binaries. Preserve image license files
   under `/usr/share/licenses/` and required notices outside that directory too.
6. Verify that recipients can obtain the matching source materials and that
   published archive hashes match the reviewed files. Current mirror URLs and
   recipe hashes alone are not an assurance of continued source availability.

The tool conservatively marks packages declaring GPL/LGPL/AGPL and several other
source-availability licenses for review. This is a triage label, not a ruling on
specific license obligations. Other packages remain subject to component review.
The custom `linux-rock5t` package is handled by the separate kernel-source lock
and must still be matched against the exact version installed in the image.

## Initial state and publication guard

The initial provisional scan found incomplete metadata for packages inherited
from the original rootfs and no fully collected/verified userspace source sets.
Use the final reports for current counts and exact package names. Do not publish
an outdated provisional list as the final image inventory. A source-code-only
repository publication does not by itself resolve binary-image redistribution.

Read-only helper tests:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/test_userspace_source_inventory.py
```
