"""Offline regression checks for the narrowly scoped Plasma 6 AC default.

These inspect overlay contents and prepare disposable image trees. They never
start PowerDevil, call systemctl, suspend the host, or exercise real hardware.
The source/enum review that establishes the key's meaning is documented in
next-version/AC-POWER-POLICY.md; these are not a simulated KConfig implementation.
"""
import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest


BASE = Path(__file__).resolve().parents[1]
ROOTFS = BASE / "rootfs"
POLICY_RELATIVE = Path("etc/xdg/powerdevilrc")
POLICY = ROOTFS / POLICY_RELATIVE
spec = importlib.util.spec_from_file_location("prepare_ac_policy", BASE / "prepare-rootfs.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def active_lines(path):
    return [line.strip() for line in path.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith(("#", ";"))]


class ACPowerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="rock5t-ac-policy-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        samples = {
            "etc/os-release": "ID=archarm\n",
            "etc/passwd": "root:x:0:0:root:/root:/bin/bash\n",
            "etc/shadow": "root:fixture-hash:1:0:99999:7:::\n",
            "etc/group": "root:x:0:\nwheel:x:10:\n",
            "etc/gshadow": "root:!::\nwheel:!::\n",
            "etc/sudoers": "root ALL=(ALL:ALL) ALL\n",
            "etc/ssh/sshd_config": "# offline fixture\n",
            "usr/lib/systemd/system/plasmalogin.service": "[Service]\nExecStart=/usr/bin/plasmalogin\n",
            "etc/systemd/logind.conf": "[Login]\n#IdleAction=ignore\n",
            "etc/systemd/sleep.conf": "[Sleep]\n#AllowSuspend=yes\n",
        }
        for target in ("sleep", "suspend", "hibernate", "hybrid-sleep", "suspend-then-hibernate"):
            samples[f"usr/lib/systemd/system/{target}.target"] = f"[Unit]\nDescription={target} fixture\n"
        for relative, content in samples.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        for relative in ("etc/sudoers.d", "var/lib/dbus", "home"):
            (self.root / relative).mkdir(parents=True, exist_ok=True)
        self.system_power_samples = {
            relative: content for relative, content in samples.items()
            if "systemd/" in relative and "plasmalogin" not in relative
        }

    def test_exact_plasma6_ac_only_default(self):
        self.assertEqual(active_lines(POLICY), [
            "[AC][SuspendAndShutdown]", "AutoSuspendAction=0",
        ])

    def test_default_is_readable_and_user_overridable(self):
        self.assertFalse(POLICY.is_symlink())
        self.assertEqual(stat.S_IMODE(POLICY.stat().st_mode), 0o644)
        self.assertNotIn("[$i]", POLICY.read_text())
        self.assertNotIn("[$d]", POLICY.read_text())

    def test_no_obsolete_or_per_user_power_profile_shipped(self):
        self.assertEqual(list(ROOTFS.rglob("powerdevilrc")), [POLICY])
        self.assertEqual(list(ROOTFS.rglob("powermanagementprofilesrc")), [])
        self.assertEqual(list(ROOTFS.rglob("kscreenlockerrc")), [])

    def test_no_global_sleep_configuration_or_masks_shipped(self):
        for relative in ("etc/systemd/sleep.conf", "etc/systemd/sleep.conf.d",
                         "etc/systemd/logind.conf", "etc/systemd/logind.conf.d"):
            self.assertFalse((ROOTFS / relative).exists(), relative)
        sleep_targets = {name + ".target" for name in (
            "sleep", "suspend", "hibernate", "hybrid-sleep", "suspend-then-hibernate",
        )}
        for path in ROOTFS.rglob("*"):
            if path.name in sleep_targets:
                self.fail(f"AC default must not replace or mask system sleep targets: {path}")

    def test_kde_preparation_copies_system_default(self):
        prepare.prepare(self.root, "kde")
        output = self.root / POLICY_RELATIVE
        self.assertEqual(output.read_bytes(), POLICY.read_bytes())
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o644)
        self.assertFalse((self.root / "etc/skel/.config/powerdevilrc").exists())

    def test_repeated_preparation_preserves_explicit_user_settings(self):
        # Existing users can intentionally override the distribution default;
        # the image policy must not rewrite their AC, battery or display choices.
        configs = {
            "home/example/.config/powerdevilrc": (
                "[AC][SuspendAndShutdown]\nAutoSuspendAction=1\n"
                "[Battery][SuspendAndShutdown]\nAutoSuspendAction=2\n"
                "[LowBattery][SuspendAndShutdown]\nAutoSuspendAction=1\n"
                "[AC][Display]\nTurnOffDisplayIdleTimeoutSec=300\n"
            ),
            "home/example/.config/kscreenlockerrc": "[Daemon]\nAutolock=true\nTimeout=10\n",
        }
        for relative, content in configs.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        for _ in range(2):
            prepare.prepare(self.root, "kde")
            self.assertEqual((self.root / POLICY_RELATIVE).read_bytes(), POLICY.read_bytes())
            for relative, content in configs.items():
                self.assertEqual((self.root / relative).read_text(), content)

    def test_both_variants_leave_system_sleep_policy_untouched(self):
        for variant in ("cli", "kde"):
            with self.subTest(variant=variant):
                prepare.prepare(self.root, variant)
                for relative, content in self.system_power_samples.items():
                    self.assertEqual((self.root / relative).read_text(), content)
                for name in ("sleep", "suspend", "hibernate", "hybrid-sleep", "suspend-then-hibernate"):
                    path = self.root / f"etc/systemd/system/{name}.target"
                    self.assertFalse(path.exists() or path.is_symlink())


if __name__ == "__main__":
    unittest.main(verbosity=2)
