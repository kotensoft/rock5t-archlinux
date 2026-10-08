# OpenSSH parser test fixtures

`sshd_config.arch-10.6` and `99-archlinux.conf` were extracted without changes
from the already-downloaded target package:

- Package: `openssh-10.6p1-1-aarch64.pkg.tar.xz`
- Package SHA-256: `28522c0cb098994889b8186315f7629bf1d75931487f16a237dd3e93bbdbaa10`
- Main config SHA-256: `7cbe2d2632fe29b0b03780b5ed6c7d5448686f236a64d143941b8839766d408d`
- Archive members: `etc/ssh/sshd_config` and
  `etc/ssh/sshd_config.d/99-archlinux.conf`

The read-only parser test changes the Include path only in its temporary copy,
adds a disposable test-only host key and PID-file path, and copies in the current
ROCK5T overlay policy. It never reads or overwrites the host SSH configuration,
starts a daemon or binds a listener. The generated test key is deleted with the
temporary directory and is not an image key or a reusable credential.

Recorded passing parser: `OpenSSH_10.0p2 Debian-7+deb13u4` with OpenSSL 3.5.7.
This is not execution of the target ARM64 10.6p1 binary.
