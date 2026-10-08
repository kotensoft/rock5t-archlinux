# ROCK5T next-version implementation and validation

This change set prepares CLI and KDE variants. It does not publish new installation images or modify a ROCK5T board.

## Implemented

- Firstboot and later NetworkManager helper: Wi-Fi device selection, scanning, hidden SSIDs, retry, skip, and later configuration. `nmcli --ask` reads passwords directly with hidden input; the wrapper does not accept passwords in arguments or record them.
- SSH setup: explicit and separate current-start, boot-enable, and regular-user password-authentication choices. Default choices are off/off/key-only. Root and the removed factory `alarm` user remain denied; access is limited to the selected non-root administrator. Policy validation fails closed. No shared credentials or debugging sudo grants.
- Firstboot permits NetworkManager only after the local account, host keys and local package trust are prepared. Display login and SSH require the final provisioning marker. Interrupted setup closes the temporary network phase.
- Kernel-generation manager retains Image, matching modules, selected ROCK5T DTB, initramfs and metadata outside the package payload. It stages depmod before publication, verifies inventories on retry, flushes directory links, protects boot-menu changes, and permits rollback to a sound previous generation if the current generation is corrupt. Pacman preflight covers install, upgrade and removal.
- KDE package profile uses `plasma-meta`, `plasma-login-manager` and Chromium. SDDM/SDDM KCM/Firefox packages and stray executables are rejected by image preparation; stale configuration is removed. Plasma Login Manager alone owns display-manager startup after provisioning. Chromium's default user flags enable `AcceleratedVideoDecoder` without changing sandbox options.
- New boot configuration retains `rt_group_sched=0`. The real-time budget stays 950000 microseconds per 1000000 microseconds; unlimited RT runtime is not enabled.
- Next-kernel packaging validates Landlock/default LSM configuration, required prior board-driver configuration, ARM64 Image, ROCK5T DTB, exact release and source-provenance fields. Existing images and historical package artifacts are not replaced.

## Completed automated checks

- 105 overlay tests passed with zero skips, including 29 kernel-generation tests, 33 firstboot/network/SSH tests, 5 real OpenSSH parser tests and the desktop-policy/regression tests.
- 7 package-gate tests passed.
- Kernel-generation tests include SIGKILL at six commit boundaries, corrupted copies, retries, package-payload removal and rollback. The original real Image/DTB/initramfs and 3593 module-tree files were preserved through an interrupted synthetic replacement.
- SSH parser checks used Debian OpenSSH 10.0p2 with the target Arch Linux ARM OpenSSH 10.6p1 configuration fixture. They opened no listener and did not change host SSH/network settings.
- Authenticated ALARM packages confirm Plasma Login Manager service, vendor PAM files, greeter account setup and plasma-meta dependency. Chromium's launcher supports the per-user flags file.
- The original kernel booted in QEMU as a negative control: Landlock syscall returned ENOSYS; the old release, default LSM list and the preserved RT settings were observed.

## Kernel build and actual runtime validation complete

The original Armbian framework source was matched by component hashes at commit fd4ebfd1e107d5b89f7a672c7d609789565753b2. All 240 board patches, 21 driver harness entries, seven pinned external driver sources and 48 driver patches are retained. The rebuilt ROCK5T DTB is byte-identical to the original. The new release is `6.18.44-current-rockchip64-landlock1`.

The Image, all modules and DTBs compiled with exit 0. All 3577 module paths match the original inventory; no path is missing or added. The output Image SHA256 is b1a97163f264bbb06b470d98fa1e68b322da073f4b78316f03f613f9a8d561c7 and is exactly the Image run in QEMU. The actual-payload packaging gate passed.

In QEMU, the default active LSM list contains Landlock and ABI 7 is available. An unprivileged UID1000 can access allowed paths and receives EACCES for denied reads and writes. The unchanged RT budget and non-root SCHED_RR inside a CPU cgroup passed. All 173 selected upstream Landlock tests passed with zero skips. This is a selected test set, not every upstream optional filesystem/network combination. Two initial pivot_root failures were caused by the special initramfs root mount; switching the test root to an ordinary tmpfs fixed both without changing the kernel or the tests. The initial failure log is preserved.

A separate test passed using both real kernel payloads, checking every module vermagic, two SIGKILL interruptions, retry, removal of temporary package payloads and bidirectional rollback. Its new initramfs is explicitly the QEMU test initramfs, so this does not establish a usable board initramfs.

Actual Arch Linux ARM pacman 7.1.0/libalpm16 was run under the new QEMU kernel with the default alpm UID/GID970, Landlock and seccomp sandbox. landlock_restrict_self returned 0. A bounded core-only download from the official mirror completed for filesystem and iana-etc (0.39 MiB), exit 0; pacman verified both signatures as valid/fully trusted and SHA256 matched the pinned core.db. Required signatures, CheckSpace and the original timeout remained enabled; no package was installed. The temporary local pacman trust key existed only in guest RAM and was destroyed at shutdown.

The broader default-mirror/full-repository test did not pass: redirects and the extra database encountered the original low-speed timeout. Direct official-mirror core/alarm/aur databases downloaded successfully; this does not fix or validate slow extra downloads. Download-timeout behavior was not changed.

## Not established by these tests

No ROCK5T boot, real Wi-Fi association, actual remote SSH login, Plasma Login Manager/Chromium hardware session, FAT power-loss recovery or board initramfs boot was tested. Manually edited unmanaged menus are deliberately rejected by preflight; in-place installation requires an explicitly reviewed migration. Hardware video/GPU/codec acceptance is outside the recorded test scope.

Evidence: `next-version/all-overlay-tests.log`, `next-version/package-gate-tests.log`, `overlay-work/tests/KERNEL-GENERATIONS.md`, `overlay-work/docs/NETWORK-SSH-NEXT.md`, and `kernel-next/logs/` plus `kernel-next/provenance/`.
