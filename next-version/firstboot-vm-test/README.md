# CLI image firstboot VM test

The actual CLI image firstboot test passed on 2026-10-08: **27/27 guest checks**,
normal guest poweroff, destroyed snapshot, and unchanged source disk SHA-256.
See `RESULTS.md` and `result-summary.json` for the verified scope.
`preflight.json` remains a host-only preparation result, not the guest result.
Future runs require a completed artifact and an explicit builder-ready signal.

## Scope and safety

- Boots the real supplied kernel, unmodified board initramfs and completed CLI GPT
  disk under QEMU `virt`, Cortex-A72, TCG, 2 vCPUs and 2048 MiB guest RAM.
- Uses `-snapshot`; hashes the source disk before and after. No production image
  or root tree is edited or mounted by the harness.
- No virtual network adapter, forwarding, host filesystem share, SSH server, or
  persistent guest access is configured. Serial is output-only; stdin is `/dev/null`.
- Controls tty1 through virtual virtio GPU and keyboard using a private local QMP
  FIFO pair. OCR waits for actual prompts. QMP keystrokes are never logged.
- Creates a random disposable administrator password only in memory, enters it
  through hidden prompts, then destroys the VM snapshot after verification.
- Chooses administrator `vmcheck`, hostname `rock5t-vm-test`, Wi-Fi skip, SSH off
  now and on future boots, and no root expansion.
- Per-process file-size limit constrains the ephemeral snapshot to 768 MiB. Each
  screenshot replaces a temporary image, with only matched prompt PNGs retained.
  Cleanup touches only this run's process and directory.
- Post-login verification uses the new administrator's password-gated sudo and a
  read-only evidence collector typed into that VM. It emits only booleans and
  nonsensitive status through the virtual serial output and powers off. It never
  exports passwords, hashes, private keys, or package-trust secret material.
- This is a **generic ARM64 userspace test**, not ROCK5T board, bootloader, DTB,
  HDMI/UART, network adapter, storage controller, or peripheral verification.
  QEMU's missing board-specific ttyS2 may fail independently; the result records
  tty1 and ttyS2 separately. Production units are not modified to hide it.

## Run after the image is ready

```
python3 run_firstboot.py --check-host
python3 run_firstboot.py --ready \
  --image /absolute/path/to/completed-cli.img \
  --kernel /absolute/path/to/that-images/Image \
  --initrd /absolute/path/to/that-images/initramfs.img
```

All artifacts are placed under `run-YYYYMMDD-HHMMSS/` in this directory. Inspect
`result.json` and the PNG evidence; `passed` requires observed real firstboot,
successful local administrator login and sudo, guest defaults verification, and
an unchanged source-image hash. A timeout or emulation limitation is reported as
blocked, not as success. The source disk's SHA-256 is recorded even on a blocked
run, and the snapshot is destroyed.

The packaged QEMU needs `QEMU_MODULE_DIR` set to the extracted host-tools module
directory or the virtio-GPU device will not be available. The harness sets it.

## Known boundaries

- OCR and the virtual framebuffer/input path were exercised successfully. Font
  OCR confuses v/u and 5/S; the bounded prompt overrides capture those variants.
- OpenSSH 10.6 `sshd -T` emits mixed-case field names. The collector normalizes
  them just as the production helper already did; the final result preserves
  the original names, successful command exit status, and effective values.
- Generated machine ID and host keys are checked for existence and permissions,
  not cross-device uniqueness. A fresh snapshot is discarded rather than reused.
- No Wi-Fi connection, remote SSH login, root growth or KDE session is tested.
- The guest collector is guarded against accidental execution on a host or a VM
  with a different hostname/root device. It must never be run directly here.

This distributable source includes only the static harness, prompt overrides and
sanitized result summary. Raw run directories, screenshots, QMP/FIFO files, serial
logs, transient snapshots and credential material are not included.
