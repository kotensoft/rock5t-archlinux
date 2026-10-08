# KDE minimal firstboot snapshot harness

These two Python files are the exact static runner/collector used for the verified
KDE snapshot on 2026-10-08. They are a separate KDE harness; the earlier CLI harness
and its successful evidence remain unchanged.

Compared with the CLI runner, this version preserves `rt_group_sched=0`, observes
the PLM welcome/account form after provisioning, then switches to tty2 for local
login and password-required sudo. The collector adds the KDE variant, PLM service
and display-manager checks. The recorded result was 31/31 with normal shutdown,
destroyed snapshot and unchanged original raw image.

## Serial framing repair

The runner accepts the JSON result only after its full CR/LF line terminator.
This prevents a truncated over-4-KiB serial chunk ending at an inner JSON brace
from being mistaken for a complete result. The guest writes a newline-terminated
record, flushes Python's stream and calls `termios.tcdrain()` before poweroff.
These are test-transport changes; production image configuration is unchanged.

Run the isolated source-level regressions without starting a VM:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 next-version/firstboot-vm-test/kde-smoke/test_transport.py
```

The suite has three framing cases and one static UART flush/drain/order assertion.
It reads the actual runner's regex from its AST and never executes the collector.
An optional `ROCK5T_INCOMPLETE_FRAME_FIXTURE` can point to the original incomplete
serial record for an additional real-fixture run; do not commit that runtime log.

A new full VM run requires the same host QEMU/OCR dependencies described in the
parent harness README, a completed KDE disk, its actual kernel and board initramfs:

```sh
python3 next-version/firstboot-vm-test/kde-smoke/run_firstboot.py --check-host
python3 next-version/firstboot-vm-test/kde-smoke/run_firstboot.py --ready \
  --image /path/to/completed-kde.img --kernel /path/to/Image --initrd /path/to/initramfs.img
```

Never run `verify_guest.py` directly on the host. It is guarded for its disposable
test guest. Tests create only random in-memory credentials and snapshot runtime;
no password, key, raw runtime log or screenshot is supplied here. The fixed account
name in source is a synthetic fixture, not a real user's identity.

Scope remains firstboot, PLM login-screen visibility, tty2 login/sudo and policy
checks. No full GUI session authentication/desktop, GPU/codec or physical-hardware
validation is implied. Recorded emulator DRM/Vulkan warnings remain in the
separately sanitized result report.
