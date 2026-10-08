# Validation at source handoff 2

Date: 2026-10-08. This is a sanitized source/evidence snapshot; final compressed
image checksums are separate release artifacts.

## Actual image and firstboot work

- CLI: 200 installed packages; 28 root-policy checks passed.
- KDE: 748 installed packages; 34 root-policy checks passed.
- Both variants passed board-initramfs preflight: 285 matching payload modules,
  expected boot hooks, Image/DTB/loader identities and partition references.
- Both variants passed eMMC root-and-boot software preflight. No physical device
  was flashed, booted or tested by these checks.
- CLI whole-disk packaging/verification completed. Its actual firstboot ran under
  generic ARM64 QEMU `virt`, Cortex-A72/TCG, with an isolated disposable snapshot.
  All 27 guest checks passed: administrator creation, local login, password-required
  sudo, firstboot identity/trust setup, policy defaults and unchanged root size.
- The VM powered off normally (exit 0), the snapshot was destroyed and the source
  raw disk SHA256 before/after was identical:
  `944b3135294b6729c21b5eeac181190ba026a7c3db4f31a9e07e6ebd6bc87837`.
- KDE disk packaging/compression verification is in progress at source freeze.
  Its graphical session and new-version ROCK5T hardware operation remain untested.

The sanitized firstboot result is `../next-version/firstboot-vm-test/result-summary.json`.
Root, board and eMMC audit summaries and actual package lists are in this directory.
Raw runtime logs, screenshots, machine/account state, private keys and source-host
paths are excluded.

## Source and tooling tests

- Recorded full overlay run: 112 passed, zero skipped, including seven scoped
  AC PowerDevil default tests. The source-only checkout rerun explicitly skips
  optional absent binary fixtures; that is not a replacement for the full run.
- Target ARM64 OpenSSH 10.6p1 parser: five tests passed. The desktop/defaults
  parser coverage alone does not establish remote SSH login.
- Kernel package gate: seven tests passed, plus the actual payload gate.
- Packaging/delivery suite: 18 tests passed, zero failed/skipped. Includes the
  real CPIO module-directory trailing-slash regression and nested JSON path
  redaction while preserving hashes/evidence. PowerShell helpers received static
  review only; no PowerShell runtime was available.
- eMMC checker policy suite: ten synthetic/read-only tests passed.
- Source-bundle helpers: two tests passed; userspace-inventory helpers: six passed.
- Handoff source whitelist comparison records exact copied production-code hashes;
  the sole code adapter explicitly skips the PLM fixture if absent from a source-only
  checkout. Public documentation/summary sanitization is recorded separately.

## Kernel and sandbox evidence

Linux `6.18.44-current-rockchip64-landlock1` compiled Image/modules/DTBs with all
3,577 original module paths retained; the ROCK5T DTB is byte-identical to the
matched authenticated Armbian package. Image SHA256:
`b1a97163f264bbb06b470d98fa1e68b322da073f4b78316f03f613f9a8d561c7`.

Generic ARM64 QEMU exposed Landlock ABI 7 and active LSMs
`capability,landlock,yama,apparmor`; unprivileged access enforcement passed.
All 173 selected upstream Landlock tests passed, zero skipped. The original
kernel negative control returned ENOSYS. Early pivot_root fixture failures were
resolved by an ordinary tmpfs test root without changing the tested kernel.
The recorded RT policy remains `rt_group_sched=0`, runtime/period
950000/1000000 microseconds. Both real kernel generations passed offline
preservation, interruption/retry and bidirectional rollback tests.

Actual ALARM pacman/libalpm ran with default Landlock/seccomp download sandbox;
a bounded core-only package download and signature/hash verification passed.
An earlier full-repository attempt encountered unchanged low-speed timeouts;
this historical network test is distinct from the completed cached package
installation and final installed package lists in this snapshot.

## Boundaries

No new-version ROCK5T board, real eMMC/SD controller, HDMI/UART, Wi-Fi/Ethernet,
remote SSH, KDE/Wayland hardware session, GPU/video-codec, FAT power-loss recovery
or actual root expansion has been validated. QEMU userspace success does not
prove board bootloader/DTB/peripheral behavior. Source-material gaps and original
recipe-provenance uncertainties are separately recorded in the userspace inventory;
no legal conclusion is inferred merely from a recipe hash mismatch.
