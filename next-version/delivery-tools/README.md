# Versioned delivery tools

The common raw GPT layout is the planned SD/eMMC compatibility approach. CLI and
KDE root+boot software audits have passed; eMMC whole-disk preparation and hardware
acceptance are still unverified. The current installation instructions prioritize
SD cards. No SPI changes are part of this workflow.

These tools do not create installation images or access hardware. The production
image entrypoint is `../../packaging-work/release_image.py`; see that directory's
README. Run `prepare_delivery.py --variant cli` (or `kde`) only after the versioned
image has completed software validation. Full `.img.xz` sources stay in the
versioned output directory. Complete images currently go only to private Library
delivery: public image publication is waiting for complete userspace source
materials, and the current public scope is limited to project-owned source.

Default Library chunks are at most 90 MiB and use three-digit ordered suffixes.
A fresh per-variant delivery folder gets copies of these Linux/Windows scripts,
Chinese notes, image reports, and checksums. `merge` validates every part, creates
a new file exclusively, and verifies the merged SHA256 before publication.
`verify` checks existing full compressed/raw artifacts; Linux also uses `xz -t`.
No script invokes a disk writer, network tool, remote API, or filesystem mount.

Each delivery folder records the actual image, ordered parts, hashes and software
validation evidence. No tool uploads files or proves a hardware boot.

Exported JSON reports recursively replace the absolute build directory prefix
with `$BUILD_ROOT/`, meaning the directory containing packaging-work/output/vm.
Source manifests and logs are preserved byte-for-byte; image/content hashes,
structure, sizes and verification outcomes are not changed. Delivery-file
checksums refer to the sanitized copies.
