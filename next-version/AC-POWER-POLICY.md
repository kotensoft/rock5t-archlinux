# ROCK5T AC automatic-suspend default

## Change

The image overlay installs `/etc/xdg/powerdevilrc`, mode 0644, containing only:

```ini
[AC][SuspendAndShutdown]
AutoSuspendAction=0
```

This supplies Plasma's AC-profile default for **no automatic suspend after idle**.
It does not set battery/low-battery profiles, power-button/lid actions, the sleep
mode, display dimming/blanking, or screen-lock options. No global systemd sleep
target is masked and no logind/sleep setting is changed. Manual suspend remains
subject to the normal desktop permissions and hardware/kernel support.

This is a normal, mutable distribution default, not a kiosk restriction. A user
can deliberately override it in Power Management or their own `powerdevilrc`.
No per-user file is seeded in `/etc/skel`. The common root overlay is copied into
both variants; the file is passive in the CLI image, which has no PowerDevil
session. It also establishes the default if Plasma is installed there later.

## Exact package and primary-source verification

Reviewed 2026-10-08 against the cached target package, without installing it:

- Archive: `arch-packages/powerdevil-6.7.5-2-aarch64.pkg.tar.xz`
- `.PKGINFO`: `pkgname = powerdevil`, `pkgver = 6.7.5-2`, `arch = aarch64`;
  packager is the Arch Linux ARM Build System.
- Archive SHA256:
  `79c63074f48ddb40e1cdf5ded14d64de3bf9b33f10c70defabfee752092b4245`
- The archive's `usr/lib/libpowerdevilcore.so.6.7.5` contains the matching
  `AutoSuspendAction` property names and `powerdevilrc` filename.

Version-specific sources in KDE's official repository mirror establish the
semantics rather than relying on older Plasma examples:

1. [PowerDevil 6.7.5 profile schema](https://github.com/KDE/powerdevil/blob/v6.7.5/PowerDevilProfileSettings.kcfg)
   names `powerdevilrc`, defines a profile-dependent parent group, and places
   the unsigned `AutoSuspendAction` key in `SuspendAndShutdown`.
2. [PowerDevil 6.7.5 action enum](https://github.com/KDE/powerdevil/blob/v6.7.5/daemon/powerdevilenums.h)
   assigns zero to `PowerButtonAction::NoAction`.
3. [PowerDevil 6.7.5 suspend action](https://github.com/KDE/powerdevil/blob/v6.7.5/daemon/actions/bundled/suspendsession.cpp)
   returns from `SuspendSession::loadAction()` before registering idle timeouts
   when that action is selected. Its explicit suspend methods invoke sleep
   separately. There is no need to force a zero timeout or disable the service.
4. [PowerDevil 6.7.5 profile selection](https://github.com/KDE/powerdevil/blob/v6.7.5/daemon/powerdevilcore.cpp)
   selects `AC` when there is no system battery or the AC adapter is plugged in;
   otherwise it selects `Battery` or `LowBattery`. Peripheral batteries are
   tracked separately. This covers the mains-powered board without requiring
   a laptop-style AC-adapter device.
5. [KDE KConfig configuration hierarchy](https://develop.kde.org/docs/features/configuration/introduction/)
   documents merging the named configuration across the XDG hierarchy and
   distinguishes normal defaults from immutable kiosk entries.
   The [XDG Base Directory specification](https://specifications.freedesktop.org/basedir/latest/)
   defines `/etc/xdg` as the fallback system configuration directory, with user
   configuration taking precedence.

The old `powermanagementprofilesrc`/`SuspendSession` layout is not written.
Package signature authentication is a separate build gate; inspecting metadata
and recording SHA256 here does not itself authenticate the package.

## Offline checks and runtime boundary

Run from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 overlay-work/tests/test_ac_power_policy.py
```

Seven tests check the exact narrow configuration, readable mode, lack of
immutability, absence of obsolete/per-user settings and global sleep masks,
copying during offline KDE preparation, repeatability, preservation of explicit
user battery/display/lock settings, and unchanged system sleep policy in both
variants. Fixtures are disposable filesystem trees; no daemon is started and
no system is suspended.

These tests establish the packaged policy and image preparation behavior. They
do not execute PowerDevil, validate board suspend/resume, or observe a real
Plasma idle period. The version-specific source review establishes the intended
setting semantics; a new-user Plasma session on the final image is still the
runtime acceptance check. On an already running target session, a read-only
check with its native `kreadconfig6` is:

```sh
kreadconfig6 --file powerdevilrc --group AC --group SuspendAndShutdown --key AutoSuspendAction
```

Expected output is `0` for a fresh user with the standard XDG configuration
search path. An explicit user override may legitimately produce another value.
If the package is changed from 6.7.5 during image assembly, review the schema,
enum and suspend-action implementation again before claiming this verification
also applies to the new version.
