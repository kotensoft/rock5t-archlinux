#!/usr/bin/env python3
"""Read-only OpenSSH parser tests; no daemon, sockets, or host config changes."""
import importlib.machinery
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

BASE = Path(__file__).resolve().parents[1]
SCRIPT = BASE / 'rootfs/usr/local/sbin/rock5t-configure-ssh'
loader = importlib.machinery.SourceFileLoader('rock5t_ssh_parser_subject', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
ssh = importlib.util.module_from_spec(spec)
loader.exec_module(ssh)
SSHD = shutil.which('sshd') or ('/usr/sbin/sshd' if Path('/usr/sbin/sshd').is_file() else None)
KEYGEN = shutil.which('ssh-keygen')


@unittest.skipUnless(SSHD and KEYGEN, 'Installed OpenSSH parser and ssh-keygen are required for read-only parser tests')
class ActualSSHParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        version = subprocess.run([SSHD, '-V'], capture_output=True, text=True)
        print('Parser binary:', (version.stderr or version.stdout).strip())
        print('Configuration fixture: Arch Linux ARM openssh 10.6p1-1; parser-only coverage, no login/listener test.')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rock5t-sshd-parser-')
        self.root = Path(self.temp.name)
        self.config = self.root/'etc/ssh/sshd_config'
        dropins = self.config.parent/'sshd_config.d'
        dropins.mkdir(parents=True)
        shutil.copyfile(BASE/'rootfs/etc/ssh/sshd_config.d/10-rock5t.conf', dropins/'10-rock5t.conf')
        shutil.copyfile(BASE/'tests/fixtures/99-archlinux.conf', dropins/'99-archlinux.conf')
        # Generate a unique disposable key because -t/-T validate host-key
        # availability. It is never installed, printed, returned or retained.
        key = self.root/'disposable-test-host-key'
        subprocess.run([KEYGEN, '-q', '-t', 'ed25519', '-N', '', '-f', str(key)],
                       check=True, capture_output=True, text=True)
        stock = (BASE/'tests/fixtures/sshd_config.arch-10.6').read_text()
        stock = stock.replace('Include /etc/ssh/sshd_config.d/*.conf', f'Include {dropins}/*.conf')
        self.config.write_text(f'HostKey {key}\nPidFile {self.root}/test-only.pid\n' + stock)
        self.manager = ssh.SSHManager(self.root, self.parser, lambda name: SimpleNamespace(pw_uid=1000))
        self.choices = {'user': 'alice', 'start_now': True, 'enable_boot': False, 'password_login': False}

    def tearDown(self):
        self.temp.cleanup()

    def parser(self, args, capture=False):
        self.assertEqual(args[0], 'sshd')
        self.assertIn(args[1], ('-t', '-T'))
        # Every call selects the temporary configuration explicitly; no call may
        # start a listener, inspect host SSH configuration or change a service.
        return subprocess.run([SSHD, *args[1:], '-f', str(self.config)],
                              capture_output=True, text=True, check=False)

    def effective(self, user):
        parsed = self.parser(['sshd', '-T', '-C', f'user={user},host=rock5t,addr=192.0.2.1'])
        self.assertEqual(parsed.returncode, 0, parsed.stderr)
        values = {}
        for line in parsed.stdout.splitlines():
            fields = line.split(None, 1)
            if len(fields) == 2:
                key, value = fields
                values.setdefault(key.lower(), []).append(value)
        return {key: ' '.join(items) for key, items in values.items()}

    def test_key_only_05_and_10_dropins_are_accepted(self):
        self.manager.install_policy(self.choices)
        for user in ('alice', 'root', 'another_user'):
            effective = self.effective(user)
            self.assertEqual(effective['permitrootlogin'], 'no')
            self.assertEqual(effective['allowusers'], 'alice')
            self.assertEqual(effective['denyusers'], 'root alarm')
            self.assertEqual(effective['passwordauthentication'], 'no')
            self.assertEqual(effective['authenticationmethods'], 'publickey')

    def test_explicit_password_policy_precedes_strict_10_defaults(self):
        self.choices['password_login'] = True
        self.manager.install_policy(self.choices)
        for user in ('alice', 'root', 'another_user'):
            effective = self.effective(user)
            self.assertEqual(effective['permitrootlogin'], 'no')
            self.assertEqual(effective['allowusers'], 'alice')
            self.assertEqual(effective['denyusers'], 'root alarm')
            self.assertEqual(effective['passwordauthentication'], 'yes')
            self.assertEqual(effective['authenticationmethods'], 'publickey password')
            self.assertEqual(effective['kbdinteractiveauthentication'], 'no')
            self.assertEqual(effective['permitemptypasswords'], 'no')

    def test_earlier_root_override_fails_closed(self):
        (self.config.parent/'sshd_config.d/00-conflict.conf').write_text('PermitRootLogin yes\n')
        with self.assertRaisesRegex(RuntimeError, 'conflicts'):
            self.manager.install_policy(self.choices)
        self.assertFalse(self.manager.config.exists())

    def test_root_match_override_fails_closed(self):
        with self.config.open('a') as config:
            config.write('\nMatch User root\n    PermitRootLogin yes\n')
        with self.assertRaisesRegex(RuntimeError, 'conflicts'):
            self.manager.install_policy(self.choices)
        self.assertFalse(self.manager.config.exists())

    def test_invalid_extra_directive_fails_closed(self):
        (self.config.parent/'sshd_config.d/00-invalid.conf').write_text('ThisIsNotAValidOption yes\n')
        with self.assertRaisesRegex(RuntimeError, 'command failed'):
            self.manager.install_policy(self.choices)
        self.assertFalse(self.manager.config.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
