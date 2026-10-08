# Final local release evidence

Release: 2026.10.08-landlock1. This small addendum updates the reviewed handoff-2
source repository's manifests and reports; production code is unchanged.

## Completed images

| Variant | Compressed bytes | Compressed SHA256 |
| --- | ---: | --- |
| CLI | 491991592 | f738a7e532bbaaa6e31c3ac42affea5c1628b2376ffbb25d32101da1facf736f |
| KDE | 1600978892 | cbd1eea9e1e4b77e93cf03ab6ae8c09113b1dd6ac418db15f1f843f16345ac6a |

Both raw images passed primary/backup GPT and protective MBR checks, loader/root
byte hashes, read-only ext4/FAT checks, boot-file inventories, extlinux references
and ROCK5T DTB identity. Compressed streams passed integrity checks and their
fully decompressed hashes equal the raw-image hashes. Full sanitized manifests
and validation reports are in `releases/2026.10.08-landlock1/`.

Actual package counts remain CLI 200 and KDE 748. Root policies passed 28/34 checks.
Both board-initramfs/eMMC root-and-boot preflights and final disk checks passed.
The eMMC result is software/offline media compatibility, not physical eMMC testing.
No eMMC/SPI device was flashed.

## Bounded VM checks

- CLI: actual firstboot snapshot passed 27/27 checks, local administrator login
  and password-required sudo, normal poweroff and destroyed snapshot. Raw SHA256
  before/after: `944b3135294b6729c21b5eeac181190ba026a7c3db4f31a9e07e6ebd6bc87837`.
- KDE: actual minimal snapshot passed 31/31 checks. The PLM login form was visibly
  present; the service was active/running, successful, with zero restarts and no
  failed units. tty2 login/password-required sudo and policy checks passed.
  `rt_group_sched=0` was preserved. Normal poweroff and snapshot destruction passed.
  Raw SHA256 before/after:
  `fc05165c08764ef8000251d40dc99b2b7fd4cb8cbcdeb592314e2194bb34e195`.
- KDE emulator logs contained DRM/Vulkan initialization and atomic-commit warnings.
  Those findings were retained, not hidden by a production change.

These tests do not include authenticating into a GUI desktop session, a complete
Plasma/Chromium session, GPU performance/codecs, real network login or physical
ROCK5T/eMMC/SD/peripheral tests. See `kde-minimal-snapshot-summary.json` and the
existing sanitized CLI firstboot result for exact checked scope.

## Source-material and publication boundaries

The final package/source inventory remains the evidence state already recorded.
`SOURCE-MATERIAL-STATUS.md` separately lists actual materials obtained, actual
source/patch/auxiliary gaps, and recipe-provenance questions. In particular, PLM's
upstream source and Arch auxiliary packaging files are present; an unmatched ARM
recipe digest alone is not a missing-source or redistribution ruling.

Local artifact verification does not establish a remote upload, a recipient's
access, or a complete license assessment. This addendum contains no binary image,
upstream source archive, internal file ID, user identity, private key or raw runtime.
