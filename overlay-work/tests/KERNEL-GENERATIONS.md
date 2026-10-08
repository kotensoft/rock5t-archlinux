# Kernel generation safety: next-version changes and executable checks

This is source-level work for a future version. No install image was rebuilt,
repackaged or released, and no running ROCK5T/device was changed.

## Changes

The manager preserves complete `Image`, selected `board.dtb`, `initramfs.img` and
runtime module trees outside pacman's file ownership. It keeps the immediately
previous release selectable in extlinux and does not garbage-collect older
releases, including a release that might still be running.

The update sequence is now:

1. Verify the mounted boot filesystem, exact managed menu and both referenced
   generations. Install, upgrade and remove all have a pre-transaction guard.
2. Validate the installed package payload's inventory, ARM64 Image magic, selected
   DTB and required module payload. Reject reserved updater bookkeeping names.
3. Copy modules into a private staging root and compare the copied files with the
   payload manifest. Run `depmod -a -b STAGING_ROOT -m /lib/modules RELEASE` there,
   before publication. A failed or interrupted depmod cannot change a published
   release. Offline assembly with an explicit initramfs uses package-provided
   indexes and does not execute target programs.
4. Write a module inventory record, flush files/directories, publish the uniquely
   named runtime module directory and flush its parent. A retry checks the full
   retained inventory instead of trusting the source-marker file alone. It never
   reruns depmod over published modules.
5. Stage Image/DTB and verify their copied bytes against the package manifest.
   Build/copy the initramfs, check it is nonempty, and recheck prepared modules
   before writing the generation's checksums. Publish and flush the complete
   boot generation. First-install directory links are flushed too.
6. Verify the complete generation. Save the old menu, then replace extlinux.conf
   last. On failure before this replacement the old selection remains intact.
   Failure after replacement can report an error even though the new selection
   is already visible: inspect `rock5t-kernel status` before reboot/retry.

A package with a reused release but changed payload is rejected. A changed
selected DTB, even if both DTBs were already in the same inventory, and a changed
explicit offline initramfs are rejected for an existing generation as well.

`rock5t-kernel rollback` verifies the recovery target independently. If the
current generation is still valid it swaps the two selections. If the current
boot files/modules are damaged or missing, it selects the intact previous
release without advertising the damaged one as a fallback. It leaves the
unselected files and saved old menu in place for diagnosis. A damaged previous
release is never selected. This changes boot selection only; it does not
downgrade pacman's installed package or other root filesystem data.

Completed legacy generations remain supported: their stored whole-module-tree
checksum is verified without requiring the new per-directory retry record.
Legacy *unfinished* module directories without that record are deliberately not
trusted for retry. After confirming a release is neither current/previous nor
running (`uname -r`), an administrator can move its incomplete files aside and
retry. Do not bypass this check by inventing a new bookkeeping file.

The menu must match the current managed rendering, including kernel.json's
cmdline. Intentional changes to either require reconciling both before the next
update; a valid marker comment alone does not authorize replacing unrelated boot
entries. Keep an external recovery copy before changing boot configuration.

## Run the tests

From `overlay-work`:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tests/test_kernel_generations.py
PYTHONDONTWRITEBYTECODE=1 python3 tests/test_overlay.py
```

The default dedicated run uses tiny, explicitly **synthetic and unbootable**
fixtures. It skips the optional real-payload case unless both inputs are given.
From the build workspace used for the recorded result:

```sh
PYTHONDONTWRITEBYTECODE=1 \
ROCK5T_REAL_PAYLOAD="$PWD/work/kernel-pkg/usr/lib/rock5t-kernel/6.18.44-current-rockchip64" \
ROCK5T_REAL_INITRAMFS="$PWD/boot-cli/rock5t/6.18.44-current-rockchip64/initramfs.img" \
python3 overlay-work/tests/test_kernel_generations.py
```

All changes occur in disposable temporary directories. No root, mounts, loop
back devices, pacman invocation or external network are needed. Input files are
copied, never modified. The real-payload case verifies every retained input
module-tree file and all three boot-file hashes against the actual package and
previously generated initramfs; it also checks the original inputs stayed
unchanged. Its replacement `6.0.0-synthetic-fixture-b` is intentionally synthetic.
It is **not a second real kernel release**, and never boots.

The dedicated tests exercise:

- Complete prior-generation retention after package payload removal and a third
  upgrade, extlinux selection and rollback through actual CLI subprocesses.
- Depmod failure after partial index writes, partial initramfs output, successful
  retry without rewriting published modules, corruption detected on retry, and
  unexpected module mutation during initramfs creation.
- SIGKILL process termination after module publication, boot-tree flush,
  generation publication, backup-menu publication, and immediately before/after
  the final menu rename. A fresh process verifies selection, retries and rolls
  back after each interruption.
- Failed filesystem flushes before generation publication and after menu rename,
  final-commit ENOSPC, low root-space rejection, and preserved earlier bytes.
- Copy-time corruption, changed DTB selection, changed explicit initramfs,
  required boot files, malformed manifest, DTB traversal, reserved names,
  altered menu paths, CLI serialization, and legacy generation compatibility.
- Rollback when the current Image is corrupt or its modules are missing, and
  refusal to roll back to a corrupt previous generation.
- Hook configuration and ordering contract. This is not an execution of pacman
  or of libalpm's hook machinery.

Full recorded output: `kernel-generations-test-results.txt`. The general overlay
suite remains a separate regression check.

## Trust, durability and verification limits

The payload manifest is an integrity inventory, **not an independent signature**.
A party able to replace both files and manifest can replace that inventory. The
package must come from a separately authenticated, trusted source, with pacman
signature checks enabled and appropriate keys. Runtime generation records are
root-owned bookkeeping, not Secure Boot, a measured-boot chain, or protection
against an administrator modifying both files and checksums. Exact kernel
release/module vermagic/DTB compatibility remains a trusted build requirement.

The supplied offline initramfs is checked for nonzero size and then retained by
hash. That is not proof that it contains the right drivers or mounts the root.
Tests using injected depmod/mkinitcpio runners check state transitions; they do
not validate actual target command output. The real-payload case uses an existing
real initramfs but does not rebuild or boot it.

SIGKILL tests show process interruption on the host filesystem. They are **not
power-cut tests**. FAT32 has no journaled cross-filesystem transaction; commit-last
rename plus fsync cannot guarantee recovery from controller caches, arbitrary
power loss or media corruption. Keep the external original recovery image.
There is no automatic failed-boot detection or automatic health-based rollback.

Process termination may leave hidden `.staging-*` or `.rock5t-modules-*`
directories. They are never advertised as completed generations. Retries ignore
them and may require free-space cleanup by an administrator if the disk is
nearly full; no automatic deletion of boot/runtime release directories occurs.
A corrupt published candidate is rejected rather than silently overwritten.

Before any future image release, a separate authorized target exercise still
needs two genuinely distinct built kernel releases (different actual `uname -r`
and matching module vermagic), real pacman pre/post hooks and mkinitcpio, normal
boot of each release, manual previous-entry selection, rollback, and interrupted
updates on a disposable target/FAT boot filesystem. This source work does not
make those claims or request changes to current hardware.

Primary command references checked for this change:

- [depmod staging-root and module-directory options](https://man.archlinux.org/man/depmod.8.en)
- [pacman hooks, AbortOnFail and post-transaction caveats](https://man.archlinux.org/man/alpm-hooks.5.en)
