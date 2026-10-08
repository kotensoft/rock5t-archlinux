#!/usr/bin/env python3
"""Apply the ROCK5T runtime overlay to an OFFLINE image tree, never the host.
Run only after package installation is complete. Re-running resets provisioning.
"""
import argparse
import os
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent


def clear(path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def write_text(path, text):
    # Replace rather than truncate files so unprivileged image assembly can update
    # owner-read-only defaults without widening their final permissions.
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    temp = path.with_name(path.name + ".rock5t-tmp")
    temp.write_text(text)
    temp.chmod(mode)
    temp.replace(path)


def replace_copy(source, destination):
    target = Path(destination)
    if target.is_file() or target.is_symlink():
        target.unlink()
    return shutil.copy2(source, destination)


def edit_accounts(root):
    etc = root / "etc"
    passwd = etc / "passwd"
    shadow = etc / "shadow"
    if not passwd.exists() or not shadow.exists():
        raise ValueError("rootfs must already contain passwd and shadow")
    for name in ("passwd", "shadow", "group", "gshadow", "subuid", "subgid"):
        p = etc / name
        if not p.exists():
            continue
        result = []
        for line in p.read_text().splitlines():
            fields = line.split(":")
            if fields[0] in {"alarm", "sddm"}:
                continue
            if name == "shadow" and fields[0] == "root":
                fields[1] = "!"  # Discard the original hash, not just prefix a lock.
            if name == "group" and len(fields) >= 4:
                fields[3] = ",".join(x for x in fields[3].split(",") if x not in {"alarm", "sddm"})
            if name == "gshadow" and len(fields) >= 4:
                fields[2:4] = [",".join(x for x in f.split(",") if x not in {"alarm", "sddm"}) for f in fields[2:4]]
            result.append(":".join(fields))
        write_text(p, "\n".join(result) + "\n")
    clear(root / "home/alarm")
    for name in ("passwd", "shadow", "group", "gshadow"):
        # User-management backup files must not retain the original default hash.
        clear(etc / (name + "-"))


def symlink(root, path, target):
    dst = root / path
    dst.parent.mkdir(parents=True, exist_ok=True)
    clear(dst)
    dst.symlink_to(target)


def prepare(root, variant):
    root = Path(root).resolve()
    if root == Path("/") or not (root / "etc/os-release").exists():
        raise ValueError("--root must be an existing offline Linux image directory, never /")
    # Refuse a running mounted root, even if reached through a bind mount.
    if os.path.samefile(root / "etc/passwd", "/etc/passwd"):
        raise ValueError("refusing to modify host accounts")
    for entry in ("etc", "usr", "var", "home"):
        if (root / entry).is_symlink():
            raise ValueError(f"top-level {entry} must not be a symlink")
    # Package removal must happen via pacman before overlay preparation, never by
    # deleting package-owned binaries behind pacman's back.
    for desc in (root / "var/lib/pacman/local").glob("*/desc"):
        lines = desc.read_text().splitlines()
        if "%NAME%" in lines:
            name = lines[lines.index("%NAME%") + 1]
            if name in {"sddm", "sddm-kcm", "firefox"}:
                raise ValueError(f"remove legacy package with pacman before preparation: {name}")
    for legacy in ("usr/bin/sddm", "usr/bin/sddm-greeter", "usr/bin/sddm-greeter-qt6", "usr/lib/sddm", "usr/bin/firefox"):
        if (root / legacy).exists() or (root / legacy).is_symlink():
            raise ValueError(f"legacy desktop executable remains after package removal: {legacy}")
    if variant == "kde" and not (root / "usr/lib/systemd/system/plasmalogin.service").is_file():
        raise ValueError("KDE requires the packaged plasmalogin.service before preparation")
    edit_accounts(root)
    shutil.copytree(HERE / "rootfs", root, dirs_exist_ok=True, copy_function=replace_copy)
    # The builder may have generated keys/IDs during package installation. Scrub last.
    (root / "etc/machine-id").write_text("")
    symlink(root, "var/lib/dbus/machine-id", "../../../etc/machine-id")
    for p in (root / "etc/ssh").glob("ssh_host_*"):
        clear(p)
    # pacman-key creates a per-install private trust key; never clone the builder's.
    clear(root / "etc/pacman.d/gnupg")
    for rel in ("etc/sddm.conf", "etc/sddm.conf.d", "var/lib/sddm", "var/cache/sddm", "home/sddm",
                "etc/pam.d/sddm", "etc/pam.d/sddm-autologin", "etc/pam.d/sddm-greeter",
                "etc/systemd/system/sddm.service", "etc/systemd/system/sddm.service.d", "etc/ssh/sshd_config.d/05-rock5t-access.conf",
                "var/lib/rock5t/ssh-choices.json", "var/lib/rock5t/ssh-choices.json.tmp",
                "run/rock5t-network-ready", "etc/NetworkManager/system-connections",
                "var/lib/NetworkManager/NetworkManager.state"):
        clear(root / rel)
    (root / "etc/NetworkManager/system-connections").mkdir(parents=True, mode=0o700, exist_ok=True)
    for directory in (root / "etc/ssh/sshd_config.d", root / "var/lib/rock5t"):
        for p in directory.glob(".rock5t-ssh-*"):
            clear(p)
    for rel in ("var/lib/systemd/random-seed", "var/lib/systemd/credential.secret", "var/lib/NetworkManager/secret_key", "var/lib/rock5t/provisioned", "var/lib/rock5t/provisioned.tmp", "var/lib/rock5t/pending-user", "var/lib/rock5t/pending-user.tmp"):
        clear(root / rel)
    (root / "var/lib/rock5t").mkdir(mode=0o700, parents=True, exist_ok=True)
    (root / "var/lib/rock5t").chmod(0o700)
    # Remove enabled SSH units/socket activation regardless of ALARM tarball defaults.
    systemd = root / "etc/systemd/system"
    for p in systemd.rglob("*"):
        if p.is_symlink() and p.name in ("sshd.service", "sshd.socket", "sshd@.service", "sddm.service"):
            p.unlink()
    for console in ("tty1", "ttyS2"):
        symlink(root, f"etc/systemd/system/multi-user.target.wants/rock5t-firstboot@{console}.service", "../rock5t-firstboot@.service")
    symlink(root, "etc/systemd/system/getty.target.wants/serial-getty@ttyS2.service", "/usr/lib/systemd/system/serial-getty@.service")
    symlink(root, "etc/systemd/system/multi-user.target.wants/NetworkManager.service", "/usr/lib/systemd/system/NetworkManager.service")
    if variant == "kde":
        clear(systemd / "getty.target.wants/getty@tty1.service")
        clear(systemd / "rock5t-provisioned.target.wants/getty@tty1.service")
        symlink(root, "etc/systemd/system/default.target", "/usr/lib/systemd/system/graphical.target")
        symlink(root, "etc/systemd/system/display-manager.service", "/usr/lib/systemd/system/plasmalogin.service")
        symlink(root, "etc/systemd/system/rock5t-provisioned.target.wants/plasmalogin.service", "/usr/lib/systemd/system/plasmalogin.service")
        flags = root / "etc/skel/.config/chromium-flags.conf"
        flags.parent.mkdir(parents=True, exist_ok=True)
        flags.write_text("--enable-features=AcceleratedVideoDecoder\n")
        mime = root / "etc/xdg/mimeapps.list"
        mime.parent.mkdir(parents=True, exist_ok=True)
        mime.write_text("[Default Applications]\nx-scheme-handler/http=chromium.desktop\nx-scheme-handler/https=chromium.desktop\ntext/html=chromium.desktop\n")
    else:
        symlink(root, "etc/systemd/system/getty.target.wants/getty@tty1.service", "/usr/lib/systemd/system/getty@.service")
        symlink(root, "etc/systemd/system/rock5t-provisioned.target.wants/getty@tty1.service", "/usr/lib/systemd/system/getty@.service")
        clear(systemd / "rock5t-provisioned.target.wants/plasmalogin.service")
        symlink(root, "etc/systemd/system/default.target", "/usr/lib/systemd/system/multi-user.target")
        clear(systemd / "display-manager.service")
    # Ensure upstream sshd configuration reads the hardening drop-in.
    sshd = root / "etc/ssh/sshd_config"
    text = sshd.read_text() if sshd.exists() else ""
    if "Include /etc/ssh/sshd_config.d/*.conf" not in text.splitlines():
        sshd.write_text("Include /etc/ssh/sshd_config.d/*.conf\n" + text)
    # Existing earlier permissive sudo rules should not survive image construction.
    sudoers = root / "etc/sudoers"
    if sudoers.exists():
        rules = sudoers.read_text()
        rules = "\n".join(line for line in rules.splitlines() if "NOPASSWD" not in line and not line.lstrip().startswith("alarm ")) + "\n"
        if "@includedir /etc/sudoers.d" not in rules and "#includedir /etc/sudoers.d" not in rules:
            rules += "@includedir /etc/sudoers.d\n"
        write_text(sudoers, rules)
        sudoers.chmod(0o440)
    for p in (root / "etc/sudoers.d").iterdir():
        if p.is_file() and not p.is_symlink():
            if "debug" in p.name.lower():
                p.unlink()
                continue
            rules = p.read_text()
            write_text(p, "\n".join(line for line in rules.splitlines() if "NOPASSWD" not in line and not line.lstrip().startswith("alarm ")) + "\n")
            p.chmod(0o440)
    (root / "etc/sudoers.d/10-rock5t-wheel").chmod(0o440)
    (root / "etc/shadow").chmod(0o600)
    print(f"Prepared {variant} image tree: {root}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--variant", choices=("cli", "kde"), required=True)
    args = parser.parse_args()
    prepare(args.root, args.variant)


if __name__ == "__main__":
    main()
