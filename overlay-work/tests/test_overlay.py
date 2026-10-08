#!/usr/bin/env python3
import importlib.machinery
import importlib.util
import json
import lzma
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
TEMPS = BASE / "tests/.tmp"
TEMPS.mkdir(exist_ok=True)


def module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


kernel = module("rock5t_kernel", BASE / "rootfs/usr/local/sbin/rock5t-kernel")
prepare = module("rock5t_prepare", BASE / "prepare-rootfs.py")
firmware = module("rock5t_firmware", BASE / "rootfs/usr/local/sbin/rock5t-expand-firmware")


class KernelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=TEMPS)
        self.root = Path(self.temp.name)
        (self.root / "etc/rock5t").mkdir(parents=True)
        (self.root / "boot").mkdir()
        (self.root / "etc/rock5t/kernel.json").write_text(json.dumps({"cmdline": "root=PARTUUID=12345678-1234-1234-1234-123456789abc rootfstype=ext4 rw rootwait console=ttyS2,1500000n8 console=tty1"}))
        self.initrd = self.root / "test-initramfs.img"
        self.initrd.write_bytes(b"test-only-initramfs")
        self.m = kernel.KernelManager(self.root, allow_unmounted=True)
        self.payload("6.18.44-rock5t-1")

    def tearDown(self):
        self.temp.cleanup()

    def payload(self, release, marker=b"module"):
        src = self.root / "usr/lib/rock5t-kernel" / release
        (src / "dtbs/rockchip").mkdir(parents=True, exist_ok=True)
        (src / "modules/kernel").mkdir(parents=True, exist_ok=True)
        (src / "Image").write_bytes(bytes(56) + b"ARM\x64" + bytes(128))
        (src / "dtbs/rockchip/rk3588-rock-5t.dtb").write_bytes(bytes.fromhex("d00dfeed") + bytes(32))
        (src / "modules/kernel/test.ko").write_bytes(marker)
        (src / "modules/modules.dep").write_text("kernel/test.ko:\n")
        data = {"format": 1, "release": release, "dtb": "rockchip/rk3588-rock-5t.dtb", "files": kernel.inventory(src, ("manifest.json",))}
        (src / "manifest.json").write_text(json.dumps(data))
        return src

    def activate(self, release="6.18.44-rock5t-1"):
        return self.m.activate(release, self.initrd)

    def test_incomplete_firmware_expansion_blocks_activation(self):
        pending = self.root / "var/lib/rock5t/firmware-expansion-pending.json"
        pending.parent.mkdir(parents=True)
        pending.write_text("{}")
        with self.assertRaisesRegex(RuntimeError, "firmware expansion did not finish"):
            self.activate()
        self.assertFalse(self.m.extlinux.exists())

    def test_initial_activation(self):
        self.assertEqual(self.activate(), {"current": "6.18.44-rock5t-1", "previous": None})
        self.m.preflight()
        cfg = self.m.extlinux.read_text()
        self.assertIn("LINUX /rock5t/6.18.44-rock5t-1/Image", cfg)
        self.assertIn("console=ttyS2,1500000n8 console=tty1", cfg)

    def test_upgrade_retains_boot_and_modules_after_pacman_payload_removal(self):
        self.activate()
        shutil.rmtree(self.m.payloads / "6.18.44-rock5t-1")
        self.payload("6.18.45-rock5t-2")
        result = self.activate("6.18.45-rock5t-2")
        self.assertEqual(result["previous"], "6.18.44-rock5t-1")
        self.m.preflight()
        self.assertIn("LABEL rock5t-previous", self.m.extlinux.read_text())
        self.assertTrue((self.m.modules / "6.18.44-rock5t-1/kernel/test.ko").exists())
        self.assertTrue(self.m.extlinux.with_name("extlinux.conf.previous").exists())

    def test_failed_pacman_transaction_leaves_current_bootable(self):
        self.activate()
        shutil.rmtree(self.m.payloads / "6.18.44-rock5t-1")
        self.m.preflight()
        self.assertEqual(self.m.state()["current"], "6.18.44-rock5t-1")

    def test_initramfs_failure_does_not_switch_selection(self):
        self.activate()
        original = self.m.extlinux.read_bytes()
        self.payload("6.18.45-rock5t-2")
        def fail(args):
            raise subprocess.CalledProcessError(1, args)
        self.m.runner = fail
        with self.assertRaises(subprocess.CalledProcessError):
            self.m.activate("6.18.45-rock5t-2")
        self.assertEqual(self.m.extlinux.read_bytes(), original)
        self.m.preflight()
        self.assertFalse((self.m.generations / "6.18.45-rock5t-2").exists())

    def test_retry_after_failed_initramfs(self):
        self.activate()
        self.payload("6.18.45-rock5t-2")
        def fail(args):
            raise subprocess.CalledProcessError(1, args)
        self.m.runner = fail
        with self.assertRaises(subprocess.CalledProcessError):
            self.m.activate("6.18.45-rock5t-2")
        self.activate("6.18.45-rock5t-2")
        self.m.preflight()

    def test_release_reuse_with_different_payload_is_rejected(self):
        self.activate()
        original = self.m.extlinux.read_bytes()
        self.payload("6.18.44-rock5t-1", marker=b"changed-module")
        with self.assertRaisesRegex(ValueError, "reused"):
            self.activate()
        self.assertEqual(self.m.extlinux.read_bytes(), original)

    def test_same_release_same_payload_is_idempotent(self):
        self.activate()
        original = self.m.extlinux.read_bytes()
        self.activate()
        self.assertEqual(self.m.extlinux.read_bytes(), original)
        self.assertIsNone(self.m.state()["previous"])

    def test_corrupt_payload_rejected(self):
        (self.m.payloads / "6.18.44-rock5t-1/Image").write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.activate()
        self.assertFalse(self.m.extlinux.exists())

    def test_corrupt_retained_modules_abort_preflight(self):
        self.activate()
        (self.m.modules / "6.18.44-rock5t-1/kernel/test.ko").write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "module checksum mismatch"):
            self.m.preflight()

    def test_payload_symlinks_rejected(self):
        (self.m.payloads / "6.18.44-rock5t-1/modules/escape").symlink_to("/etc/passwd")
        with self.assertRaisesRegex(ValueError, "symlinks"):
            self.activate()

    def test_unmounted_boot_rejected(self):
        self.m.allow_unmounted = False
        with self.assertRaisesRegex(RuntimeError, "not mounted"):
            self.activate()

    def test_unmanaged_boot_configuration_is_not_overwritten(self):
        self.m.extlinux.parent.mkdir()
        self.m.extlinux.write_text("DEFAULT vendor\n")
        with self.assertRaisesRegex(RuntimeError, "not ROCK5T-managed"):
            self.activate()
        self.assertEqual(self.m.extlinux.read_text(), "DEFAULT vendor\n")

    def test_full_boot_partition_does_not_change_current(self):
        self.activate()
        original = self.m.extlinux.read_bytes()
        self.payload("6.18.45-rock5t-2")
        usage = shutil.disk_usage(self.root)
        with patch.object(kernel.shutil, "disk_usage", return_value=usage._replace(free=0)):
            with self.assertRaisesRegex(RuntimeError, "insufficient /boot space"):
                self.activate("6.18.45-rock5t-2")
        self.assertEqual(self.m.extlinux.read_bytes(), original)

    def test_manual_rollback_swaps_complete_generations(self):
        self.activate()
        self.payload("6.18.45-rock5t-2")
        self.activate("6.18.45-rock5t-2")
        result = self.m.select_previous()
        self.assertEqual(result, {"current": "6.18.44-rock5t-1", "previous": "6.18.45-rock5t-2"})
        self.m.preflight()


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=TEMPS)
        self.root = Path(self.temp.name)
        for d in ("etc/ssh", "etc/sudoers.d", "etc/pacman.d/gnupg/private-keys-v1.d", "usr/share/pacman/keyrings", "usr/lib/systemd/system", "var/lib/dbus", "var/lib/systemd", "home/alarm", "usr"):
            (self.root / d).mkdir(parents=True, exist_ok=True)
        samples = {
            "etc/os-release": "ID=archarm\n", "etc/passwd": "root:x:0:0:root:/root:/bin/bash\nalarm:x:1000:1000::/home/alarm:/bin/bash\n",
            "etc/shadow": "root:default-root-hash:1:0:99999:7:::\nalarm:default-alarm-hash:1:0:99999:7:::\n",
            "etc/shadow-": "root:default-root-hash:1:0:99999:7:::\n", "etc/group": "root:x:0:\nwheel:x:10:alarm\nalarm:x:1000:\n",
            "etc/gshadow": "wheel:!::alarm\nalarm:!::\n", "etc/sudoers": "root ALL=(ALL:ALL) ALL\n%wheel ALL=(ALL) NOPASSWD: ALL\n",
            "etc/sudoers.d/old": "alarm ALL=(ALL) ALL\n%wheel ALL=(ALL) NOPASSWD: ALL\n", "etc/ssh/sshd_config": "# SSH config\n",
            "etc/pacman.d/gnupg/private-keys-v1.d/example.key": "builder-secret-pacman-key",
            "usr/share/pacman/keyrings/archlinuxarm.gpg": "public-alarm-keyring",
            "usr/share/pacman/keyrings/archlinux.gpg": "public-arch-keyring",
            "usr/lib/systemd/system/plasmalogin.service": "[Service]\nExecStart=/usr/bin/plasmalogin\n",
            "etc/ssh/ssh_host_ed25519_key": "private-key", "etc/machine-id": "reused-machine-id", "var/lib/systemd/random-seed": "reused-seed",
        }
        for rel, data in samples.items():
            (self.root / rel).write_text(data)

    def tearDown(self):
        self.temp.cleanup()

    def test_secure_cli_preparation(self):
        prepare.prepare(self.root, "cli")
        self.assertIn("root:!:", (self.root / "etc/shadow").read_text())
        for name in ("passwd", "shadow", "group", "gshadow"):
            self.assertNotIn("alarm", (self.root / "etc" / name).read_text())
        self.assertFalse((self.root / "etc/shadow-").exists())
        self.assertFalse((self.root / "home/alarm").exists())
        self.assertFalse((self.root / "etc/ssh/ssh_host_ed25519_key").exists())
        self.assertEqual((self.root / "etc/machine-id").read_text(), "")
        self.assertTrue((self.root / "var/lib/dbus/machine-id").is_symlink())
        self.assertFalse((self.root / "var/lib/systemd/random-seed").exists())
        self.assertNotIn("NOPASSWD", (self.root / "etc/sudoers.d/old").read_text())
        self.assertFalse((self.root / "var/lib/rock5t/provisioned").exists())
        self.assertEqual((self.root / "etc/systemd/system/default.target").readlink(), Path("/usr/lib/systemd/system/multi-user.target"))
        self.assertTrue((self.root / "etc/systemd/system/multi-user.target.wants/rock5t-firstboot@ttyS2.service").is_symlink())

    def test_pacman_private_trust_key_is_scrubbed_public_rings_retained(self):
        prepare.prepare(self.root, "cli")
        self.assertFalse((self.root / "etc/pacman.d/gnupg").exists())
        self.assertEqual((self.root / "usr/share/pacman/keyrings/archlinuxarm.gpg").read_text(), "public-alarm-keyring")
        self.assertEqual((self.root / "usr/share/pacman/keyrings/archlinux.gpg").read_text(), "public-arch-keyring")

    def test_firstboot_trust_initialization_precedes_provisioning_commit(self):
        script = (BASE / "rootfs/usr/local/sbin/rock5t-firstboot").read_text()
        init = script.index("pacman-key --init")
        populate = script.index("pacman-key --populate archlinuxarm archlinux")
        commit = script.index('mv "$state/provisioned.tmp" "$complete"')
        self.assertLess(init, populate)
        self.assertLess(populate, commit)
        self.assertIn("set -Eeuo pipefail", script)
        self.assertGreater(script.index('rm -f "$state/pending-user"'), populate)

    def test_firstboot_accepts_only_the_two_physical_consoles(self):
        script = (BASE / "rootfs/usr/local/sbin/rock5t-firstboot").read_text()
        self.assertIn('case "$console" in tty1|ttyS2) ;; *) exit 64 ;; esac', script)
        self.assertIn('[[ $(tty) == /dev/"$console" ]]', script)

    def test_kde_preparation_gates_display_manager(self):
        prepare.prepare(self.root, "kde")
        self.assertEqual((self.root / "etc/systemd/system/default.target").readlink(), Path("/usr/lib/systemd/system/graphical.target"))
        self.assertTrue((self.root / "etc/systemd/system/rock5t-provisioned.target.wants/plasmalogin.service").is_symlink())
        self.assertFalse((self.root / "etc/systemd/system/getty.target.wants/getty@tty1.service").is_symlink())
        self.assertFalse((self.root / "etc/systemd/system/rock5t-provisioned.target.wants/getty@tty1.service").is_symlink())
        self.assertIn("ConditionPathExists=/var/lib/rock5t/provisioned", (self.root / "etc/systemd/system/plasmalogin.service.d/10-rock5t-provisioning.conf").read_text())

    def test_rejects_host_root(self):
        with self.assertRaisesRegex(ValueError, "never /"):
            prepare.prepare(Path("/"), "cli")

    def test_preparation_is_repeatable(self):
        prepare.prepare(self.root, "cli")
        prepare.prepare(self.root, "cli")
        self.assertEqual((self.root / "etc/ssh/sshd_config").read_text().count("Include /etc/ssh/sshd_config.d/*.conf"), 1)


class FirmwareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=TEMPS)
        self.root = Path(self.temp.name)
        self.fw = self.root / "usr/lib/firmware"
        self.fw.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def compressed(self, name="rtl_nic/rtl8125b-2.fw", data=b"firmware-v1"):
        p = self.fw / (name + ".xz")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(lzma.compress(data))
        return p

    def test_expand_preserves_compressed_original(self):
        source = self.compressed()
        original = source.read_bytes()
        self.assertEqual(firmware.expand(self.root), 1)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(source.with_suffix("").read_bytes(), b"firmware-v1")

    def test_upgrade_and_remove_managed_companions(self):
        source = self.compressed()
        firmware.expand(self.root)
        source.write_bytes(lzma.compress(b"firmware-v2"))
        firmware.expand(self.root)
        self.assertEqual(source.with_suffix("").read_bytes(), b"firmware-v2")
        source.unlink()
        self.assertEqual(firmware.expand(self.root), 0)
        self.assertFalse(source.with_suffix("").exists())

    def test_preserves_relative_symlinks(self):
        source = self.compressed("vendor/actual.bin")
        alias = self.fw / "vendor/alias.bin.xz"
        alias.symlink_to("actual.bin.xz")
        firmware.expand(self.root)
        self.assertEqual(alias.with_suffix("").readlink(), Path("actual.bin"))
        self.assertEqual(alias.with_suffix("").read_bytes(), b"firmware-v1")
        self.assertEqual(alias.readlink(), Path("actual.bin.xz"))

    def test_package_owned_raw_file_wins(self):
        source = self.compressed()
        source.with_suffix("").write_bytes(b"package-owned-raw")
        files = self.root / "var/lib/pacman/local/test-firmware-1/files"
        files.parent.mkdir(parents=True)
        files.write_text("%FILES%\nusr/lib/firmware/rtl_nic/rtl8125b-2.fw\n")
        self.assertEqual(firmware.expand(self.root), 0)
        self.assertEqual(source.with_suffix("").read_bytes(), b"package-owned-raw")

    def test_refuses_to_overwrite_local_modifications(self):
        source = self.compressed()
        firmware.expand(self.root)
        source.with_suffix("").write_bytes(b"local-change")
        source.write_bytes(lzma.compress(b"upgrade"))
        with self.assertRaisesRegex(ValueError, "locally modified"):
            firmware.expand(self.root)
        self.assertEqual(source.with_suffix("").read_bytes(), b"local-change")

    def test_bad_archive_preserves_previous_output(self):
        source = self.compressed()
        firmware.expand(self.root)
        source.write_bytes(b"bad archive")
        with self.assertRaises(lzma.LZMAError):
            firmware.expand(self.root)
        self.assertEqual(source.with_suffix("").read_bytes(), b"firmware-v1")
        self.assertEqual(list(source.parent.glob(".rock5t-fw-*")), [])

    def test_zstd_runs_to_temporary_output(self):
        source = self.fw / "mali.bin.zst"
        source.write_bytes(b"test-zstd")
        def zstd(args, stdout, check):
            self.assertEqual(args[0], "zstd")
            self.assertEqual(args[-1], str(source))
            stdout.write(b"mali-raw")
        firmware.expand(self.root, zstd_runner=zstd)
        self.assertEqual(source.with_suffix("").read_bytes(), b"mali-raw")


if __name__ == "__main__":
    unittest.main(verbosity=2)
