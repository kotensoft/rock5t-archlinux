# Next-version firstboot network and SSH code

This is implementation and mock-test work only. It does not build or release an
installation image. No target-board, actual Wi-Fi, or actual SSH-server test was
performed. The existing image deliverables are unchanged.

## Local setup and interruption

Firstboot retains the `tty1`/`ttyS2` allowlist, actual terminal check, single
`flock`, pending administrator, mandatory password re-entry after interruption,
and final `/var/lib/rock5t/provisioned` commit. It initializes the account, unique
identity, package trust and password-required sudo before optional networking.

Only NetworkManager gets a temporary firstboot allowance:
`/run/rock5t-network-ready`. Its systemd drop-in must OR that allowance with the
final provisioned marker. Getty, desktop and SSH units keep their final-marker
requirement. The temporary marker is owned by the firstboot console that holds
the lock; it is not a second provisioning-completion marker.

On interruption, that console asks NetworkManager to disable networking, stops
NetworkManager, and removes the temporary gate. The next setup attempt also
cleans a stale gate before re-locking the pending account. This cleanup is
best-effort if NetworkManager/systemd themselves fail. Final-marker service
protection still applies. After successful setup, NetworkManager is started and
networking re-enabled even if the retry skipped Wi-Fi, so a previous interruption
cannot leave a persistent networking-off state unnoticed. These cleanup actions
never run for an already-provisioned device.

A failure after committing provisioning still schedules the normal-services
target. The target starts asynchronously because desktop/getty ordering waits
for the firstboot services to leave their consoles.

## Wi-Fi wizard and later configuration

Run later from an authenticated terminal:

```sh
sudo rock5t-configure-network
```

- Skip before opting in makes no network changes.
- NetworkManager remains the only network owner; no direct `wpa_supplicant`,
  `dhcpcd`, `systemd-networkd`, or ad hoc interface configuration is used.
- Supports interface selection, live scan, exact SSID entry, hidden SSIDs,
  retry after failed activation, missing-adapter handling, and configure-later.
- Uses `nmcli --ask device wifi connect`; nmcli reads its own password directly
  from the terminal with echo disabled. No secret is collected by Python or Bash,
  placed in process arguments, written to wizard logs, or echoed with
  `--show-secrets`. Firstboot also disables shell command tracing.
- NetworkManager saves the resulting device-specific profile and credentials
  using its normal protected storage. Credentials are not written into the
  overlay. Offline image preparation must scrub builder profiles.
- Intended for the network types supported by `nmcli device wifi connect`.
  Enterprise/802.1X setup needs a suitable NetworkManager profile after local
  sign-in. SSIDs with control characters or more than 32 UTF-8 bytes are rejected.
- Connection activation success is not an Internet-connectivity test.
- The later helper requires sudo, a completed provisioning marker and interactive
  input/output. It never stops the user's existing networking on a skip, failed
  attempt or exit. An opted-in new connection may naturally replace the selected
  interface's current connection.

## SSH choices

Run later from an authenticated terminal:

```sh
sudo rock5t-configure-ssh
# To select another existing regular account deliberately:
sudo rock5t-configure-ssh --user another_admin
```

The wizard asks separately whether to start SSH now, enable it for future boots,
and explicitly permit this administrator's existing account password for SSH.
All answers default to no. Key-only login remains the default if access is
requested. The user must install their own public key locally; no user private
key, reusable key pair, shared password, or passwordless sudo rule is created.

Current and future-boot states are independent:

- No / no: stop sshd and disable its future-boot link
- Yes / no: start sshd now and disable its future-boot link
- No / yes: leave sshd stopped now and enable its future-boot link
- Yes / yes: start sshd now and enable its future-boot link

Any existing SSH socket activation is disabled/stopped before these choices
are applied, so it cannot quietly defeat a disabled-server choice. Existing
SSH sessions may survive stopping the main daemon, as with normal systemd/OpenSSH
behavior; this wizard does not forcibly terminate authenticated sessions.

SSH access is limited to the explicitly selected administrator through
`AllowUsers`. Root and alarm are always denied. Password login, when explicitly
chosen, is an alternative to public-key authentication for that account only.
Keyboard-interactive and empty-password authentication remain disabled. The
managed policy contains no `Match` blocks that could alter the parsing context
of the distribution's later SSH configuration.

Files written at runtime:

- `/etc/ssh/sshd_config.d/05-rock5t-access.conf`: independent managed SSH policy,
  before the shipped strict `10-rock5t.conf` defaults
- `/var/lib/rock5t/ssh-choices.json`: username plus three booleans, no credentials

Both are atomically replaced, fsynced, and mode 0600. A failed `sshd -t` or
conflicting effective `sshd -T -C` policy restores the previous policy and does
not proceed to service enablement. The effective administrator and root policy
is checked. Administrators should use this helper or deliberately maintain
compatible additional sshd configuration; arbitrary custom address/group Match
rules are not exhaustively enumerated by this check.

During firstboot, policy, choices and boot enablement are saved while the SSH
service's final-marker gate is still closed. Requested current access starts only
after the final marker. Consequently, a power loss after the final marker cannot
lose a selected future-boot enablement. Failure applying the current service
state leaves a clear local retry command. The later helper refuses to start SSH
without a completed provisioning marker.

## Offline preparation integration

The offline-only preparation step should remove:

- `var/lib/rock5t/ssh-choices.json`
- `etc/ssh/sshd_config.d/05-rock5t-access.conf`
- `.rock5t-ssh-*` atomic temporary files alongside those two files
- `run/rock5t-network-ready`
- Any builder NetworkManager profiles, credentials and persistent
  `NetworkManager.state` that could preserve a networking-disabled state

It must retain the shipped strict SSH policy and final-marker gates for
`sshd.service`, normal gettys and the desktop. Existing socket-activation links
must remain removed. These are fresh-image cleanup instructions, not a request
to erase configuration on an installed user's device.

## Tests and verification

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tests/test_network_ssh.py
PYTHONDONTWRITEBYTECODE=1 python3 tests/test_overlay.py
PYTHONDONTWRITEBYTECODE=1 python3 tests/test_ssh_parser.py
bash -n rootfs/usr/local/sbin/rock5t-firstboot
```

The dedicated mock suite has 33 tests. Wi-Fi and SSH commands use mock runners; the
firstboot shell harness maps every mutable path into a temporary directory and
replaces every system-changing command with a fake executable. It exercises
actual shell flow for success, interrupted package trust, interrupted networking,
stale gate cleanup, and an already-provisioned no-op. No host network, accounts,
SSH config, daemon state, or hardware is touched. Existing 29 overlay tests also
passed, along with shell syntax and Python compilation. ShellCheck is unavailable
in this workspace.

A separate five-test suite uses the real installed OpenSSH 10.0p2
Debian-7+deb13u4 parser against temporary configuration and disposable unique
host keys, with `-t`/`-T -f` only. It starts no listener and reads no host SSH
configuration. The configuration fixture is from the actual Arch Linux ARM
`openssh-10.6p1-1` package, including its `99-archlinux.conf` drop-in. It verifies
05+10+99 ordering, both authentication choices, earlier/global and root-Match
conflicts, and invalid directives. All five pass. This caught and fixed repeated
DenyUsers output handling: real `sshd -T` emits one line per list entry. The
parser binary version differs from the target 10.6p1 binary, so this is syntax
and effective-policy coverage, not target executable or login verification.
Tests skip explicitly if no parser or ssh-keygen executable is installed.

These tests do not certify a physical adapter, driver, access point, UART,
concurrent physical consoles, login authentication, or systemd on the target.
Those remain unverified; none were started as part of this code-only task.

## Primary references

- [NetworkManager nmcli manual](https://networkmanager.dev/docs/api/latest/nmcli.html):
  interactive `--ask`, hidden-SSID connection, Wi-Fi scanning and networking off/on
- [OpenSSH sshd_config manual](https://man.openbsd.org/sshd_config.5):
  first-value semantics, AllowUsers/DenyUsers and alternative authentication methods
