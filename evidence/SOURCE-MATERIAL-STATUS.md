# Source-material status at final artifact handoff

The image build/validation result and source-material inventory answer different
questions. No legal conclusion is inferred merely from a recipe hash mismatch.
The metadata inventory covers the actual installed CLI 200/KDE 748 packages,
748 unique versions and 685 recipe identities. It contains 656 cached recipe
hashes, 91 repository-index-only records and the separately handled custom kernel.

## Actual source and auxiliary material obtained

- Linux and the matched open-source boot stack: eleven pinned upstream archives,
  audited configuration/build scripts, notices and a separately archived complete
  actual patched Linux source tree are retained outside Git. No proprietary DDR
  bytes are included in that generic source collection; its exact notice is retained.
- Plasma Login Manager 6.7.5: the actual upstream source archive was obtained and
  its SHA256 matches the exact Arch recipe. The exact Arch packaging archive,
  including auxiliary files, is also present. Do not describe PLM as having no
  source merely because the ARM binary's recorded recipe hash is not matched.
- Bash: the exact Arch packaging directory/auxiliary files were obtained. Its
  actual base source, complete 001–020 patch sequence and associated checks remain
  uncollected in this bounded review.
- glibc, pacman and systemd: recipe candidates/history leads exist; relevant pinned
  upstream source snapshots and complete ARM distribution patches/auxiliary
  build/install files remain to be collected or verified as individually recorded.
- Chromium: an exact-version upstream source endpoint and recipe checksum were
  verified as available, but the 1,878,222,540-byte source archive was not downloaded.
  The exact ARM patches/auxiliaries and incorporated component material still need
  their own inspection. A package-level BSD label is not a full component inventory.

## Separate original-build provenance questions

The original ARM PKGBUILD bytes/transformation have not been established for
several reviewed packages. Matching `.BUILDINFO` is strong exact-byte provenance
when obtainable; lack of that match alone does not determine the sufficiency of
actual corresponding-source materials or whether distribution is permitted.
For PLM, the remaining uncertainty must be described together with the source and
Arch auxiliary files already obtained, rather than as a blanket missing-source
claim. No complete per-component assessment or certification is claimed here.

The six representative reviews, obtained-material hashes, actual material gaps
and provenance gaps are separate fields in `userspace-sources-final.json`.
Further license/source tracing stopped at that recorded evidence state; this final
artifact addendum does not invent new source availability or publish an image.
