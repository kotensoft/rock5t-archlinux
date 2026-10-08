import json
import os
from pathlib import Path
import subprocess
import tarfile
import unittest

import test_overlay as legacy
prepare, BASE = legacy.prepare, legacy.BASE

PROJECT = BASE.parent


class NextDesktopTests(unittest.TestCase):
    setUp = legacy.PrepareTests.setUp
    tearDown = legacy.PrepareTests.tearDown
    def test_installed_sddm_is_rejected_before_account_changes(self):
        desc = self.root / 'var/lib/pacman/local/sddm-1/desc'
        desc.parent.mkdir(parents=True)
        desc.write_text('%NAME%\nsddm\n\n')
        old = (self.root / 'etc/shadow').read_bytes()
        with self.assertRaisesRegex(ValueError, 'remove legacy package'):
            prepare.prepare(self.root, 'kde')
        self.assertEqual((self.root / 'etc/shadow').read_bytes(), old)

    def test_missing_plm_fails_closed(self):
        (self.root / 'usr/lib/systemd/system/plasmalogin.service').unlink()
        with self.assertRaisesRegex(ValueError, 'requires the packaged'):
            prepare.prepare(self.root, 'kde')

    def test_unregistered_legacy_daemon_is_also_rejected(self):
        daemon = self.root / 'usr/bin/sddm'
        daemon.parent.mkdir(parents=True)
        daemon.write_text('stale fixture')
        with self.assertRaisesRegex(ValueError, 'legacy desktop executable'):
            prepare.prepare(self.root, 'kde')

    def test_old_credentials_and_display_configuration_are_scrubbed(self):
        for rel in ['etc/sddm.conf', 'etc/sddm.conf.d/old.conf', 'var/lib/sddm/state.conf',
                    'etc/NetworkManager/system-connections/test.nmconnection',
                    'var/lib/NetworkManager/NetworkManager.state', 'run/rock5t-network-ready',
                    'etc/ssh/sshd_config.d/05-rock5t-access.conf',
                    'etc/ssh/sshd_config.d/.rock5t-ssh-old',
                    'var/lib/rock5t/ssh-choices.json', 'var/lib/rock5t/.rock5t-ssh-old',
                    'etc/sudoers.d/99-debug-access']:
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('BUILD_SECRET_FIXTURE')
        prepare.prepare(self.root, 'kde')
        self.assertFalse(any('BUILD_SECRET_FIXTURE' in p.read_text(errors='ignore')
                             for p in self.root.rglob('*') if p.is_file() and not p.is_symlink()))
        self.assertEqual((self.root / 'etc/systemd/system/display-manager.service').readlink(),
                         Path('/usr/lib/systemd/system/plasmalogin.service'))
        self.assertFalse((self.root / 'etc/systemd/system/sddm.service.d').exists())

    def test_chromium_profile_contains_only_requested_acceleration(self):
        prepare.prepare(self.root, 'kde')
        flags = (self.root / 'etc/skel/.config/chromium-flags.conf').read_text()
        self.assertEqual(flags, '--enable-features=AcceleratedVideoDecoder\n')
        self.assertNotIn('sandbox', flags)
        self.assertIn('chromium.desktop', (self.root / 'etc/xdg/mimeapps.list').read_text())

    def test_transient_network_gate_does_not_unlock_desktop(self):
        prepare.prepare(self.root, 'kde')
        nm = (self.root / 'etc/systemd/system/NetworkManager.service.d/10-rock5t-provisioning.conf').read_text()
        plm = (self.root / 'etc/systemd/system/plasmalogin.service.d/10-rock5t-provisioning.conf').read_text()
        self.assertIn('ConditionPathExists=|/run/rock5t-network-ready', nm)
        self.assertIn('ConditionPathExists=|/var/lib/rock5t/provisioned', nm)
        self.assertNotIn('network-ready', plm)
        self.assertIn('ConditionPathExists=/var/lib/rock5t/provisioned', plm)

    def test_realtime_budget_not_unlimited(self):
        text = (BASE / 'rootfs/etc/sysctl.d/90-rock5t-realtime-budget.conf').read_text()
        self.assertIn('kernel.sched_rt_runtime_us = 950000', text)
        self.assertIn('kernel.sched_rt_period_us = 1000000', text)
        self.assertNotIn('= -1', text)
        self.assertIn('rt_group_sched=0', (PROJECT / 'scripts/finalize-target.sh').read_text())

    def test_package_profile_uses_meta_plm_and_chromium(self):
        packages = (PROJECT / 'profiles/kde.packages').read_text().splitlines()
        for name in ['plasma-meta', 'plasma-login-manager', 'chromium']:
            self.assertIn(name, packages)
        for name in ['sddm', 'sddm-kcm', 'firefox']:
            self.assertNotIn(name, packages)

    def test_packaged_plm_has_pam_and_correct_service(self):
        package_dir = Path(os.environ.get('ROCK5T_TEST_PACKAGES', PROJECT / 'next-version/research/packages'))
        package = next(package_dir.glob('plasma-login-manager-*.pkg.tar.xz'), None)
        if package is None:
            self.skipTest('Set ROCK5T_TEST_PACKAGES to verified package fixtures for the binary PLM test')
        with tarfile.open(package) as archive:
            names = archive.getnames()
            self.assertIn('usr/lib/pam.d/plasmalogin', names)
            service = archive.extractfile('usr/lib/systemd/system/plasmalogin.service').read().decode()
            self.assertIn('Alias=display-manager.service', service)
            self.assertIn('ExecStart=/usr/bin/plasmalogin', service)


if __name__ == '__main__':
    unittest.main(verbosity=2)
