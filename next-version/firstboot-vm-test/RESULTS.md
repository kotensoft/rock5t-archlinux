# Actual CLI firstboot userspace test

**PASS: 27/27 checks.** Sanitized public result: `result-summary.json`.
Run completed on 2026-10-08 at approximately 15:18 UTC.

## What ran

The completed `archlinux-rock5t-cli-2026.10.08-landlock1.img` GPT disk booted with
the actual `6.18.44-current-rockchip64-landlock1` kernel Image and its unmodified
board initramfs under QEMU `virt` / Cortex-A72 / TCG. The disk was attached with
`-snapshot`, 2048 MiB guest RAM, and a 768 MiB maximum snapshot-file size.
There was no NIC, host share, remote login, serial stdin, or production mutation.
Management used private mode-0600 FIFO files under this test directory.

The unmodified tty1 firstboot service:

1. Created a fresh non-root administrator with a random disposable password.
2. Applied the requested test hostname and hosts entry.
3. Generated the machine identity, SSH host keys, and local pacman trust key;
   populated both distribution keyrings offline.
4. Accepted Wi-Fi skip, SSH current state off and future boots off, and no growth.
5. Committed provisioning and handed off to ordinary local login.

The administrator then logged in and completed password-required sudo.
A read-only guest collector verified all 27 assertions, including root locked,
alarm absent, wheel membership, password set, identity/trust generation,
provisioning cleanup, disabled/inactive SSH service and socket, public-key-only
SSH policy limited to the new user, root/alarm denied, no user authorized key,
and unchanged root partition size (8,388,608 sectors). `systemctl --failed` was
empty, and tty1's firstboot result was success with exit status 0.

The guest powered off normally (QEMU exit 0). Its snapshot and temporary FIFO
files were destroyed. No test password or private key was exported.

## Source integrity

- CLI raw disk before/after: `944b3135294b6729c21b5eeac181190ba026a7c3db4f31a9e07e6ebd6bc87837`
- Kernel Image: `b1a97163f264bbb06b470d98fa1e68b322da073f4b78316f03f613f9a8d561c7`
- Board initramfs: `95f057dcf7a1438e1e163523c8b7db1f94066d2ecd5fece66993f5cd151e03f4`

The public summary preserves the input/output hashes, all 27 boolean checks,
root-partition geometry, normal QEMU exit and snapshot-destruction result.
Raw runtime logs, screenshots, command/backing-file paths and account details
are excluded from this source package.

## Test-harness corrections

Early attempts required the supported local FIFO management transport and OCR
prompt matching adjustments. The final collector normalized OpenSSH 10.6 output
field names with `key.lower()`, matching the production helper's existing behavior.
These were test-harness corrections; no production SSH-policy change was needed.
The final run completed with `sshd -T` exit 0, no failed units and all checks true.

## Not covered

This is generic ARM64 virtual-machine userspace evidence. It does **not** verify
ROCK5T bootloader/DTB, real HDMI/UART, storage controllers or other peripherals,
KDE/Wayland, actual Wi-Fi/Ethernet connectivity, remote SSH access, root expansion,
or cross-device identity uniqueness. Physical ROCK5T tests were explicitly skipped.
The final ttyS2 unit status does not establish real board-UART functionality.
